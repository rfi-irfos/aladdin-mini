"""
Aladdin Mini — Bayesian enforcement calibrator.

Inspired by Santander AI Lab's auto-bayesian (Apache 2.0).
github.com/rfi-irfos/auto-bayesian (fork)

Trains a BayesianNetwork on historical disclosure enforcement outcomes using
pgmpy. With few empirical anchors the Bayesian posterior is blended with the
deterministic model estimate (weight grows as more outcomes are recorded).

Nodes:
  dpa_tier  : 0=Tier-1 (DPC/CNPD), 1=Tier-2 (BayLDA/ICO), 2=Tier-3/4
  severity  : 0=HIGH (>=7), 1=MED (4-6), 2=LOW (<4)
  prior_fine: 0=YES prior fine, 1=NO prior fine
  enforced  : 0=NO enforcement, 1=YES enforcement  ← target
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Optional

try:
    import pandas as pd
    from pgmpy.inference import VariableElimination
    try:
        from pgmpy.models import DiscreteBayesianNetwork as BayesianNetwork
    except ImportError:
        from pgmpy.models import BayesianNetwork
    _PGMPY = True
except ImportError:
    _PGMPY = False

from .params import DisclosureParams


# ── Empirical anchors ──────────────────────────────────────────────────────
# Each row is a confirmed enforcement outcome.
# Source: public regulatory decisions + settlement records.
_SEED_DATA = [
    # Amazon CNPD Luxembourg — €746M (2021)
    {"dpa_tier": 0, "severity": 0, "prior_fine": 0, "enforced": 1},
    # Meta DSB Ireland — €1.2B (2023)
    {"dpa_tier": 0, "severity": 0, "prior_fine": 0, "enforced": 1},
    # Meta DSB — €390M (2023, separate investigation)
    {"dpa_tier": 0, "severity": 0, "prior_fine": 0, "enforced": 1},
    # British Airways ICO — £20M (2020)
    {"dpa_tier": 1, "severity": 0, "prior_fine": 1, "enforced": 1},
    # Marriott ICO — £18.4M (2020)
    {"dpa_tier": 1, "severity": 0, "prior_fine": 1, "enforced": 1},
    # Equifax FTC/CFPB — $700M (2019, US)
    {"dpa_tier": 2, "severity": 0, "prior_fine": 1, "enforced": 1},
    # H&M GDPR Hamburg — €35.3M (2020)
    {"dpa_tier": 1, "severity": 0, "prior_fine": 1, "enforced": 1},
    # Tier-3 DPA, medium severity → no action (representative non-enforcement)
    {"dpa_tier": 2, "severity": 1, "prior_fine": 1, "enforced": 0},
    {"dpa_tier": 2, "severity": 1, "prior_fine": 1, "enforced": 0},
    {"dpa_tier": 2, "severity": 2, "prior_fine": 1, "enforced": 0},
    # Tier-2 DPA, medium severity, no prior → typically no action
    {"dpa_tier": 1, "severity": 1, "prior_fine": 1, "enforced": 0},
    # Tier-1 DPA, low severity → sometimes no formal enforcement
    {"dpa_tier": 0, "severity": 2, "prior_fine": 1, "enforced": 0},
]


@dataclass
class CalibrationResult:
    original_enforcement_prob: float
    calibrated_enforcement_prob: float
    bayesian_posterior: float
    blend_weight: float          # 0 = all model, 1 = all Bayesian
    n_historical: int
    dpa_tier_bin: int
    severity_bin: int
    prior_fine_bin: int
    available: bool = True       # False if pgmpy not installed


def _discretize(p: DisclosureParams) -> tuple[int, int, int]:
    """Map continuous params to Bayesian network bins."""
    dpa = p.lead_dpa_tier - 1  # 1→0, 2→1, 3→2, 4→2
    dpa = min(2, max(0, dpa))
    sev = 0 if p.severity_score >= 7 else (1 if p.severity_score >= 4 else 2)
    prior = 0 if p.prior_fine_count > 0 else 1
    return dpa, sev, prior


class BayesianCalibrator:
    """Train once, calibrate many times.

    Usage:
        cal = BayesianCalibrator()
        cal.fit()
        result = cal.calibrate(params, model_enforcement_prob)
    """

    def __init__(self, extra_data: Optional[list[dict]] = None):
        self._trained = False
        self._model: Optional[object] = None
        self._inference: Optional[object] = None
        self._n = len(_SEED_DATA) + (len(extra_data) if extra_data else 0)
        self._extra = extra_data or []

    def fit(self) -> "BayesianCalibrator":
        if not _PGMPY:
            return self
        all_rows = _SEED_DATA + self._extra
        df = pd.DataFrame(all_rows)

        edges = [
            ("dpa_tier", "enforced"),
            ("severity", "enforced"),
            ("prior_fine", "enforced"),
        ]
        model = BayesianNetwork(edges)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(df)
        self._model = model
        self._inference = VariableElimination(model)
        self._trained = True
        return self

    def calibrate(
        self,
        p: DisclosureParams,
        model_enforcement_prob: float,
    ) -> CalibrationResult:
        dpa, sev, prior = _discretize(p)

        if not _PGMPY or not self._trained:
            return CalibrationResult(
                original_enforcement_prob=model_enforcement_prob,
                calibrated_enforcement_prob=model_enforcement_prob,
                bayesian_posterior=model_enforcement_prob,
                blend_weight=0.0,
                n_historical=0,
                dpa_tier_bin=dpa,
                severity_bin=sev,
                prior_fine_bin=prior,
                available=False,
            )

        result = self._inference.query(
            variables=["enforced"],
            evidence={"dpa_tier": dpa, "severity": sev, "prior_fine": prior},
            show_progress=False,
        )
        bayes_p = float(result.values[1])  # P(enforced=1)

        # Blend weight: grows with sqrt of historical cases, maxes at 0.6
        # With 12 seeds: weight ≈ 0.35 (still mostly model-driven)
        blend = min(0.60, (self._n ** 0.5) / 20.0)
        calibrated = (1.0 - blend) * model_enforcement_prob + blend * bayes_p

        return CalibrationResult(
            original_enforcement_prob=model_enforcement_prob,
            calibrated_enforcement_prob=round(calibrated, 4),
            bayesian_posterior=round(bayes_p, 4),
            blend_weight=round(blend, 3),
            n_historical=self._n,
            dpa_tier_bin=dpa,
            severity_bin=sev,
            prior_fine_bin=prior,
            available=True,
        )

    def add_outcome(self, p: DisclosureParams, enforced: bool) -> None:
        """Record a new resolved disclosure outcome for future training rounds."""
        dpa, sev, prior = _discretize(p)
        self._extra.append({
            "dpa_tier": dpa,
            "severity": sev,
            "prior_fine": prior,
            "enforced": int(enforced),
        })
        self._n += 1
        self._trained = False  # invalidate; call fit() again


# module-level default calibrator (lazy fit on first use)
_DEFAULT_CALIBRATOR: Optional[BayesianCalibrator] = None


def get_calibrator() -> BayesianCalibrator:
    global _DEFAULT_CALIBRATOR
    if _DEFAULT_CALIBRATOR is None:
        _DEFAULT_CALIBRATOR = BayesianCalibrator().fit()
    return _DEFAULT_CALIBRATOR


def calibrate(p: DisclosureParams, enforcement_prob: float) -> CalibrationResult:
    """Convenience function: calibrate using the module-level default calibrator."""
    return get_calibrator().calibrate(p, enforcement_prob)
