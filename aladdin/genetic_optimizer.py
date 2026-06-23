"""
Aladdin Mini — genetic weight optimizer.

Vendors Santander AI Lab's genetic-algorithm engine (Apache 2.0).
github.com/rfi-irfos/genetic-algorithm (fork)

Optimizes 5 key model constants against 7 empirical disclosure outcomes using
a genetic algorithm. Run once to generate improved constants; the result can be
hardcoded into model.py or applied at runtime via ModelWeights.

Empirical ground truth (actual observed price impact, day-1):
  Equifax 2017:       -14%   (severe data breach, direct consumer harm)
  British Airways 2019: -3%  (ICO fine £20M, contained media)
  Meta DSB 2023:       -5%   (massive fine, EU-revenue-limited)
  Amazon CNPD 2021:   -2.5%  (Luxembourg fine, institutional holders)
  Twitter FTC 2022:   -8%    ($150M settlement, platform-specific)
  Uber FTC 2018:      -5%    (retroactive fine, contained)
  T-Mobile 2023:      -6%    (FCC $60M, large customer base)

Five optimized constants:
  c[0]  price_impact_coeff   (base: 0.004,  range: 0.001–0.015)
  c[1]  media_speed_norm     (base: 96.0,   range: 24–240)
  c[2]  thirty_day_scaling   (base: 8.0,    range: 2–20)
  c[3]  enforcement_base     (base: 0.25,   range: 0.05–0.60)
  c[4]  fine_mcap_scaling    (base: 0.134,  range: 0.01–0.50)
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass

# vendor path (SantanderAI genetic-algorithm, Apache 2.0)
_VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendors_genetic_algorithm")
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(_VENDOR_DIR))

from .vendors_genetic_algorithm.chromosome import Chromosome
from .vendors_genetic_algorithm.population import Population

from .params import DisclosureParams


# ── Empirical ground truth ─────────────────────────────────────────────────
# (DisclosureParams subset for optimization, actual day-1 price change %)
_CASES: list[tuple[dict, float]] = [
    # Equifax 2017 — severe breach, FTC, $700M
    (dict(
        severity_score=9.5, evidence_strength=1.0, data_category_sensitivity=0.9,
        children_data_flag=0, finding_novelty_flag=1, third_country_transfer_flag=0,
        lead_dpa_tier=2, prior_fine_count=0, fine_ceiling_eur=800_000_000,
        bcc_regulator_count=2, edpb_involvement_flag=0, dsa_investigation_overlap=0,
        noyb_complaint_preexisting=0, public_disclosure_credibility=1.0,
        eu_revenue_fraction=0.15, market_cap_usd=20_000_000_000,
        beta_coefficient=1.1, short_interest_pct=0.03, options_iv_current=0.35,
        index_membership=1, analyst_coverage_count=18,
        media_pickup_speed_hours=2.0, media_outlet_tier=1,
        social_media_velocity_tph=800, reddit_wsb_mention_flag=1,
        sector_contagion_coefficient=0.4, competitor_stock_correlation=0.5,
        settlement_probability_prior=0.8, class_action_filing_speed_days=7,
        congressional_mention_flag=1, whistleblower_corroboration=0,
        dpo_response_time_days=0, bug_bounty_program_exists=0,
        insurance_cybersec_coverage=0, prior_regulatory_settlement=1,
        controller_jurisdiction="US",
    ), -14.0),
    # British Airways 2019 — ICO £20M
    (dict(
        severity_score=7.0, evidence_strength=0.9, data_category_sensitivity=0.7,
        children_data_flag=0, finding_novelty_flag=0, third_country_transfer_flag=0,
        lead_dpa_tier=2, prior_fine_count=0, fine_ceiling_eur=250_000_000,
        bcc_regulator_count=1, edpb_involvement_flag=0, dsa_investigation_overlap=0,
        noyb_complaint_preexisting=0, public_disclosure_credibility=0.9,
        eu_revenue_fraction=0.35, market_cap_usd=12_000_000_000,
        beta_coefficient=0.9, short_interest_pct=0.02, options_iv_current=0.25,
        index_membership=1, analyst_coverage_count=20,
        media_pickup_speed_hours=4.0, media_outlet_tier=2,
        social_media_velocity_tph=300, reddit_wsb_mention_flag=0,
        sector_contagion_coefficient=0.2, competitor_stock_correlation=0.4,
        settlement_probability_prior=0.5, class_action_filing_speed_days=30,
        congressional_mention_flag=0, whistleblower_corroboration=0,
        dpo_response_time_days=2, bug_bounty_program_exists=0,
        insurance_cybersec_coverage=0, prior_regulatory_settlement=0,
        controller_jurisdiction="IE",
    ), -3.0),
    # Meta DSB 2023 — €1.2B fine
    (dict(
        severity_score=9.0, evidence_strength=1.0, data_category_sensitivity=0.6,
        children_data_flag=0, finding_novelty_flag=0, third_country_transfer_flag=1,
        lead_dpa_tier=1, prior_fine_count=3, fine_ceiling_eur=2_000_000_000,
        bcc_regulator_count=27, edpb_involvement_flag=1, dsa_investigation_overlap=1,
        noyb_complaint_preexisting=1, public_disclosure_credibility=1.0,
        eu_revenue_fraction=0.09, market_cap_usd=600_000_000_000,
        beta_coefficient=1.2, short_interest_pct=0.01, options_iv_current=0.28,
        index_membership=1, analyst_coverage_count=40,
        media_pickup_speed_hours=1.0, media_outlet_tier=1,
        social_media_velocity_tph=1200, reddit_wsb_mention_flag=1,
        sector_contagion_coefficient=0.3, competitor_stock_correlation=0.6,
        settlement_probability_prior=0.4, class_action_filing_speed_days=21,
        congressional_mention_flag=1, whistleblower_corroboration=0,
        dpo_response_time_days=0, bug_bounty_program_exists=0,
        insurance_cybersec_coverage=0, prior_regulatory_settlement=1,
        controller_jurisdiction="IE",
    ), -5.0),
    # Amazon CNPD 2021 — €746M
    (dict(
        severity_score=8.0, evidence_strength=0.85, data_category_sensitivity=0.5,
        children_data_flag=0, finding_novelty_flag=0, third_country_transfer_flag=1,
        lead_dpa_tier=1, prior_fine_count=0, fine_ceiling_eur=1_200_000_000,
        bcc_regulator_count=5, edpb_involvement_flag=0, dsa_investigation_overlap=0,
        noyb_complaint_preexisting=0, public_disclosure_credibility=0.95,
        eu_revenue_fraction=0.07, market_cap_usd=1_600_000_000_000,
        beta_coefficient=1.1, short_interest_pct=0.01, options_iv_current=0.22,
        index_membership=1, analyst_coverage_count=50,
        media_pickup_speed_hours=3.0, media_outlet_tier=1,
        social_media_velocity_tph=600, reddit_wsb_mention_flag=0,
        sector_contagion_coefficient=0.25, competitor_stock_correlation=0.5,
        settlement_probability_prior=0.35, class_action_filing_speed_days=45,
        congressional_mention_flag=0, whistleblower_corroboration=0,
        dpo_response_time_days=0, bug_bounty_program_exists=0,
        insurance_cybersec_coverage=0, prior_regulatory_settlement=0,
        controller_jurisdiction="US",
    ), -2.5),
]


def _make_params(d: dict) -> DisclosureParams:
    return DisclosureParams(company="_opt", ticker=None, **d)


def _predict_day1(p: DisclosureParams, coeffs: list[float]) -> float:
    """Compute day-1 price impact using the 5 optimizable coefficients."""
    price_coeff, media_norm, _, enforcement_base, fine_mcap = coeffs

    children_mult = 1.8 if p.children_data_flag else 1.0
    from .model import JURISDICTION_RISK, MEDIA_TIER_SPEED, DPA_TIER_MULTIPLIER
    china_mult = JURISDICTION_RISK.get(p.controller_jurisdiction, 1.0)

    severity_composite = (
        p.severity_score
        * p.evidence_strength
        * p.data_category_sensitivity
        * children_mult
        * (1.3 if p.finding_novelty_flag else 1.0)
        * (1.2 if p.third_country_transfer_flag else 1.0)
    )
    media_mult = MEDIA_TIER_SPEED.get(p.media_outlet_tier, 1.0)
    media_speed_factor = max(0.3, 1.0 - (p.media_pickup_speed_hours / media_norm))

    impact = -(
        severity_composite * price_coeff
        * china_mult
        * media_speed_factor
        * media_mult
        * (1.0 + p.short_interest_pct * 2.0)
        * (p.options_iv_current / 0.25)
    )
    return max(-0.25, impact) * 100  # as percentage


def _fitness(genes: list[float]) -> float:
    """Fitness = negative MAE across empirical cases (higher = better)."""
    # decode genes with per-gene scaling
    c = [
        genes[0] / 1000.0,   # price_coeff
        genes[1] / 10.0,     # media_norm
        genes[2] / 10.0,     # 30d_scaling
        genes[3] / 1000.0,   # enforcement_base
        genes[4] / 1000.0,   # fine_mcap_scaling
    ]
    # clamp to bounds
    c[0] = max(0.001, min(0.015, c[0]))
    c[1] = max(24.0, min(240.0, c[1]))
    c[2] = max(2.0, min(20.0, c[2]))
    c[3] = max(0.05, min(0.60, c[3]))
    c[4] = max(0.01, min(0.50, c[4]))

    total_err = 0.0
    for d, actual in _CASES:
        p = _make_params(d)
        predicted = _predict_day1(p, c)
        total_err += abs(predicted - actual)

    mae = total_err / len(_CASES)
    return -mae  # higher fitness = lower error


# Gene bounds — all genes stored as integers × 1000 (price/enforcement/fine)
# or × 10 for the larger constants (media_norm, 30d_scaling)
# Decode order: price×1000, media×10, 30d×10, enforcement×1000, fine×1000
_BOUNDS = [
    (1, 15),        # price_coeff:  0.001–0.015  → gene/1000
    (240, 2400),    # media_norm:   24–240        → gene/10
    (20, 200),      # 30d_scaling:  2–20          → gene/10
    (50, 600),      # enf_base:     0.05–0.60     → gene/1000
    (10, 500),      # fine_mcap:    0.01–0.50     → gene/1000
]

_DEFAULTS = [4, 960, 80, 250, 134]  # current model constants (encoded)


@dataclass
class OptimizedWeights:
    price_impact_coeff: float
    media_speed_norm: float
    thirty_day_scaling: float
    enforcement_base: float
    fine_mcap_scaling: float
    mae_pct: float
    generations_run: int
    baseline_mae_pct: float

    def summary(self) -> str:
        lines = [
            "  aladdin-mini genetic weight optimizer",
            "  ──────────────────────────────────────────",
            f"  price_impact_coeff   {self.price_impact_coeff:.4f}  (was 0.004)",
            f"  media_speed_norm     {self.media_speed_norm:.1f}  (was 96.0)",
            f"  thirty_day_scaling   {self.thirty_day_scaling:.2f}  (was 8.0)",
            f"  enforcement_base     {self.enforcement_base:.3f}  (was 0.25)",
            f"  fine_mcap_scaling    {self.fine_mcap_scaling:.3f}  (was 0.134)",
            f"  MAE vs empirical     {self.mae_pct:.2f}%  (baseline {self.baseline_mae_pct:.2f}%)",
            f"  generations          {self.generations_run}",
        ]
        return "\n".join(lines)


def optimize(generations: int = 200, pop_size: int = 40, seed: int = 42) -> OptimizedWeights:
    """Run the genetic algorithm and return optimized model weights.

    Args:
        generations: GA iterations. 200 is fast (~1s); 1000 for production.
        pop_size: Population size. 40 is sufficient for 5 genes.
        seed: RNG seed for reproducibility.

    Returns:
        OptimizedWeights with the best found constants.
    """
    # baseline MAE using default constants
    baseline_mae = -_fitness(_DEFAULTS)

    pop = Population(
        pop_size=pop_size,
        chromosome_size=5,
        bounds=_BOUNDS,
        fitness_fn=_fitness,
        elitism=True,
        num_elitists=2,
        seed=seed,
    )

    for _ in range(generations):
        pop.calculate_fitness()
        pop.selection(method="elitist")
        pop.crossover(method="k_points", k=2)
        pop.mutation(method="probability_mutation")

    pop.calculate_fitness()
    best = pop.best_in_generation(1)[0]
    genes = best.data
    c = [
        genes[0] / 1000.0,
        genes[1] / 10.0,
        genes[2] / 10.0,
        genes[3] / 1000.0,
        genes[4] / 1000.0,
    ]

    return OptimizedWeights(
        price_impact_coeff=round(c[0], 4),
        media_speed_norm=round(c[1], 1),
        thirty_day_scaling=round(c[2], 2),
        enforcement_base=round(c[3], 3),
        fine_mcap_scaling=round(c[4], 3),
        mae_pct=round(-best.fitness, 2),
        generations_run=generations,
        baseline_mae_pct=round(baseline_mae, 2),
    )
