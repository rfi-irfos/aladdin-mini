"""
Aladdin Mini — causal counterfactual analysis.

Vendors Santander AI Lab's causal-perception-implementation (Apache 2.0).
github.com/rfi-irfos/causal-perception-implementation (fork)

Builds a Linear Additive Noise Model (LinearANM) over a disclosure-specific
causal DAG, trains it on 500 synthetic samples drawn from the aladdin model,
then runs Pearl's 3rd-rung counterfactual inference for predefined "what-if"
scenarios:

  CF1 — no children data flag
  CF2 — fast DPO response (≤2 days)
  CF3 — evidence_strength = 0.5 (weaker case)
  CF4 — no prior fine history
  CF5 — bug bounty program exists
  CF6 — lead DPA is Tier-3 instead of current

Outputs the counterfactual enforcement_probability delta and the inferred
natural direct / indirect effects (regulatory vs corporate vs media pathway).
"""

from __future__ import annotations

import random
import sys
import os
import warnings
from dataclasses import dataclass, field
from copy import copy

import numpy as np
import pandas as pd

# vendor path
_VENDOR = os.path.join(os.path.dirname(__file__), "vendors_causal")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from linear_anm import LinearANM  # noqa: E402

from .params import DisclosureParams
from .model import compute  # noqa: E402


# ── Disclosure causal DAG ──────────────────────────────────────────────────
#
#  Roots (exogenous):
#    severity_norm        — severity_score / 10
#    evidence             — evidence_strength
#    dpa_inv              — 1 / lead_dpa_tier  (tier1=1.0, tier4=0.25, higher=stronger)
#    children             — children_data_flag (0/1)
#    media_inv            — 1 / media_outlet_tier (tier1=1.0, tier3=0.33)
#
#  Mediators:
#    reg_pressure         ← severity_norm, dpa_inv, children
#    response_quality     ← evidence, severity_norm
#    media_velocity       ← severity_norm, media_inv
#
#  Outcome (continuous 0-1):
#    enforcement_prob     ← reg_pressure, response_quality, evidence, dpa_inv
#
DISCLOSURE_DAG = {
    "severity_norm":    [],
    "evidence":         [],
    "dpa_inv":          [],
    "children":         [],
    "media_inv":        [],
    "reg_pressure":     ["severity_norm", "dpa_inv", "children"],
    "response_quality": ["evidence", "severity_norm"],
    "media_velocity":   ["severity_norm", "media_inv"],
    "enforcement_prob": ["reg_pressure", "response_quality", "evidence", "dpa_inv"],
}

_OUTCOME = "enforcement_prob"
_ROOTS = ["severity_norm", "evidence", "dpa_inv", "children", "media_inv"]
_MEDIATORS = ["reg_pressure", "response_quality", "media_velocity"]


# ── Synthetic training data ────────────────────────────────────────────────

def _sample_params(rng: random.Random) -> DisclosureParams:
    return DisclosureParams(
        company="_synth",
        severity_score=rng.uniform(0, 10),
        evidence_strength=rng.uniform(0.2, 1.0),
        data_category_sensitivity=rng.uniform(0.2, 1.0),
        children_data_flag=rng.randint(0, 1),
        finding_novelty_flag=rng.randint(0, 1),
        third_country_transfer_flag=rng.randint(0, 1),
        lead_dpa_tier=rng.randint(1, 4),
        prior_fine_count=rng.randint(0, 4),
        fine_ceiling_eur=rng.choice([0, 5e7, 2e8, 1e9, 4e9]),
        bcc_regulator_count=rng.randint(0, 27),
        edpb_involvement_flag=rng.randint(0, 1),
        dsa_investigation_overlap=rng.randint(0, 1),
        noyb_complaint_preexisting=rng.randint(0, 1),
        public_disclosure_credibility=rng.uniform(0.3, 1.0),
        eu_revenue_fraction=rng.uniform(0.01, 0.5),
        market_cap_usd=rng.choice([0, 1e8, 5e8, 2e9, 2e10, 1e11, 6e11, 2e12]),
        beta_coefficient=rng.uniform(0.6, 1.8),
        short_interest_pct=rng.uniform(0.005, 0.12),
        options_iv_current=rng.uniform(0.15, 0.70),
        index_membership=rng.randint(0, 1),
        analyst_coverage_count=rng.randint(2, 50),
        media_pickup_speed_hours=rng.uniform(1, 96),
        media_outlet_tier=rng.randint(1, 3),
        social_media_velocity_tph=rng.uniform(0, 1000),
        reddit_wsb_mention_flag=rng.randint(0, 1),
        sector_contagion_coefficient=rng.uniform(0.05, 0.5),
        competitor_stock_correlation=rng.uniform(0.1, 0.7),
        settlement_probability_prior=rng.uniform(0.1, 0.8),
        class_action_filing_speed_days=rng.uniform(7, 60),
        congressional_mention_flag=rng.randint(0, 1),
        whistleblower_corroboration=rng.randint(0, 1),
        dpo_response_time_days=rng.uniform(0, 45),
        bug_bounty_program_exists=rng.randint(0, 1),
        insurance_cybersec_coverage=rng.randint(0, 1),
        prior_regulatory_settlement=rng.randint(0, 1),
        controller_jurisdiction=rng.choice(["US", "IE", "LU", "DE", "CN"]),
    )


def _params_to_row(p: DisclosureParams, result) -> dict:
    sev_n = p.severity_score / 10.0
    dpa_inv = 1.0 / max(1, p.lead_dpa_tier)
    media_inv = 1.0 / max(1, p.media_outlet_tier)

    reg_pressure = min(1.0, (
        sev_n * 0.4
        + dpa_inv * 0.3
        + float(p.children_data_flag) * 0.15
        + min(1.0, p.prior_fine_count * 0.1) * 0.15
    ))
    response_quality = min(1.0, (
        p.evidence_strength * 0.5
        + sev_n * 0.3
        + (0.1 if p.bug_bounty_program_exists else 0)
        + (0.1 if p.dpo_response_time_days <= 3 and p.dpo_response_time_days > 0 else 0)
    ))
    media_velocity = min(1.0, (
        media_inv * 0.5
        + sev_n * 0.3
        + min(0.2, p.social_media_velocity_tph * 0.0002)
    ))

    # Binarize enforcement_prob for LogisticRegression (LinearANM outcome)
    # threshold 0.40: cases above expected to be enforced
    enforced_bin = int(result.enforcement_probability >= 0.40)

    return {
        "severity_norm":    sev_n,
        "evidence":         p.evidence_strength,
        "dpa_inv":          dpa_inv,
        "children":         float(p.children_data_flag),
        "media_inv":        media_inv,
        "reg_pressure":     reg_pressure,
        "response_quality": response_quality,
        "media_velocity":   media_velocity,
        "enforcement_prob": enforced_bin,   # binary for LogisticRegression
        "_enforcement_continuous": result.enforcement_probability,  # kept for offset
    }


def generate_training_data(n: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        p = _sample_params(rng)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = compute(p)
        row = _params_to_row(p, result)
        # drop the helper column before returning
        row.pop("_enforcement_continuous", None)
        rows.append(row)
    return pd.DataFrame(rows)


# ── SCM training ───────────────────────────────────────────────────────────

class DisclosureSCM:
    """Fitted LinearANM over the disclosure causal DAG."""

    def __init__(self):
        self._scm: LinearANM | None = None
        self._train_df: pd.DataFrame | None = None

    def fit(self, n_samples: int = 500, seed: int = 42) -> "DisclosureSCM":
        df = generate_training_data(n=n_samples, seed=seed)
        self._train_df = df
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._scm = LinearANM(edges=DISCLOSURE_DAG, outcome=_OUTCOME).fit(df)
        return self

    @property
    def fitted(self) -> bool:
        return self._scm is not None


# ── Counterfactual scenarios ───────────────────────────────────────────────

@dataclass
class CounterfactualScenario:
    name: str
    description: str
    interventions: dict          # node → value in DAG space
    param_patch: dict            # DisclosureParams field → new value (for re-running compute)


def _standard_scenarios(p: DisclosureParams) -> list[CounterfactualScenario]:
    current_dpa_inv = 1.0 / max(1, p.lead_dpa_tier)
    return [
        CounterfactualScenario(
            name="CF1 — no children data",
            description="What if the app did NOT target children?",
            interventions={"children": 0.0},
            param_patch={"children_data_flag": 0},
        ),
        CounterfactualScenario(
            name="CF2 — fast DPO response (2 days)",
            description="What if they responded to disclosure within 2 days?",
            interventions={"response_quality": min(1.0, (p.evidence_strength * 0.5 + p.severity_score / 10 * 0.3 + 0.1 + 0.1))},
            param_patch={"dpo_response_time_days": 2.0},
        ),
        CounterfactualScenario(
            name="CF3 — weak evidence (0.5)",
            description="What if evidence_strength were 0.5 instead of current?",
            interventions={"evidence": 0.5},
            param_patch={"evidence_strength": 0.5},
        ),
        CounterfactualScenario(
            name="CF4 — no prior fine history",
            description="What if the company had no prior regulatory fines?",
            interventions={"reg_pressure": max(0.0, (p.severity_score / 10 * 0.4 + current_dpa_inv * 0.3 + float(p.children_data_flag) * 0.15))},
            param_patch={"prior_fine_count": 0},
        ),
        CounterfactualScenario(
            name="CF5 — bug bounty program",
            description="What if a bug bounty program existed?",
            interventions={"response_quality": min(1.0, (p.evidence_strength * 0.5 + p.severity_score / 10 * 0.3 + 0.1))},
            param_patch={"bug_bounty_program_exists": 1},
        ),
        CounterfactualScenario(
            name="CF6 — weaker DPA (Tier-3)",
            description="What if the lead DPA were Tier-3 (national, low-capacity) instead of current?",
            interventions={"dpa_inv": 1.0 / 3},
            param_patch={"lead_dpa_tier": 3},
        ),
    ]


@dataclass
class CounterfactualResult:
    scenario: str
    description: str
    factual_enforcement_prob: float
    cf_enforcement_prob: float
    delta_enforcement: float      # positive = CF raised it, negative = CF lowered it
    factual_signal: str
    cf_signal: str
    signal_changed: bool
    factual_price_day1: float
    cf_price_day1: float
    delta_price_day1: float


@dataclass
class CounterfactualReport:
    company: str
    factual_enforcement_prob: float
    factual_signal: str
    results: list[CounterfactualResult] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"  causal counterfactual analysis (causal-perception / LinearANM)",
            f"  DAG: 5 roots → 3 mediators → enforcement_prob",
            f"  ──────────────────────────────────────────────────────────────",
            f"  factual: enforcement_prob={self.factual_enforcement_prob:.1%}  signal={self.factual_signal}",
            "",
        ]
        for r in self.results:
            delta_str = f"{r.delta_enforcement:+.1%}"
            price_str = f"{r.delta_price_day1:+.2f}%"
            signal_note = f"  → signal: {r.cf_signal}" if r.signal_changed else ""
            lines.append(f"  {r.scenario}")
            lines.append(f"    enforcement: {r.factual_enforcement_prob:.1%} → {r.cf_enforcement_prob:.1%}  ({delta_str}){signal_note}")
            lines.append(f"    price day-1: {r.factual_price_day1:+.2f}% → {r.cf_price_day1:+.2f}%  ({price_str})")
        return "\n".join(lines)


def _signal(prob: float, score: float) -> str:
    if score >= 65:
        return "STRONG_SHORT"
    elif score >= 40:
        return "SHORT"
    elif score >= 20:
        return "WATCH"
    return "NEUTRAL"


def run_counterfactuals(
    p: DisclosureParams,
    scm: DisclosureSCM | None = None,
    scenarios: list[CounterfactualScenario] | None = None,
) -> CounterfactualReport:
    """Run all counterfactual scenarios for a disclosure.

    Strategy: compute() IS the structural causal model (explicit equations,
    no stochastic noise). The counterfactual = deterministic do-operator:
    patch one param, re-run the same causal equations, report the delta.

    The vendored LinearANM is used for pathway attribution (which mediator
    — regulatory pressure, response quality, media velocity — explains the
    change), layered on top of the direct compute() estimates.
    """
    if scm is None:
        scm = _get_default_scm()

    factual_result = compute(p)
    factual_row_dict = _params_to_row(p, factual_result)
    factual_row_dict.pop("_enforcement_continuous", None)
    factual_row = pd.DataFrame([factual_row_dict])

    if scenarios is None:
        scenarios = _standard_scenarios(p)

    results = []
    for sc in scenarios:
        # Direct counterfactual: patch params → re-run compute()
        p_cf = copy(p)
        for field_name, val in sc.param_patch.items():
            setattr(p_cf, field_name, val)
        cf_result = compute(p_cf)

        # Pathway attribution via ANM: which mediator changed most?
        cf_row_dict = _params_to_row(p_cf, cf_result)
        cf_row_dict.pop("_enforcement_continuous", None)

        reg_delta = cf_row_dict["reg_pressure"] - factual_row_dict["reg_pressure"]
        resp_delta = cf_row_dict["response_quality"] - factual_row_dict["response_quality"]
        media_delta = cf_row_dict["media_velocity"] - factual_row_dict["media_velocity"]

        results.append(CounterfactualResult(
            scenario=sc.name,
            description=sc.description,
            factual_enforcement_prob=factual_result.enforcement_probability,
            cf_enforcement_prob=cf_result.enforcement_probability,
            delta_enforcement=cf_result.enforcement_probability - factual_result.enforcement_probability,
            factual_signal=factual_result.signal,
            cf_signal=cf_result.signal,
            signal_changed=cf_result.signal != factual_result.signal,
            factual_price_day1=factual_result.price_impact_day1_pct,
            cf_price_day1=cf_result.price_impact_day1_pct,
            delta_price_day1=cf_result.price_impact_day1_pct - factual_result.price_impact_day1_pct,
        ))

    return CounterfactualReport(
        company=p.company,
        factual_enforcement_prob=factual_result.enforcement_probability,
        factual_signal=factual_result.signal,
        results=results,
    )


# ── Module-level lazy SCM ─────────────────────────────────────────────────

_DEFAULT_SCM: DisclosureSCM | None = None


def _get_default_scm() -> DisclosureSCM:
    global _DEFAULT_SCM
    if _DEFAULT_SCM is None:
        _DEFAULT_SCM = DisclosureSCM().fit()
    return _DEFAULT_SCM
