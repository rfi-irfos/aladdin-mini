"""
Aladdin Mini — causality model engine.
Computes cascade outputs from the 50-parameter disclosure profile.
"""

import math
from dataclasses import dataclass
from .params import DisclosureParams


JURISDICTION_RISK = {"CN": 1.6, "US": 1.2, "IE": 0.9, "LU": 0.85, "DE": 0.8}
DPA_TIER_MULTIPLIER = {1: 1.5, 2: 1.2, 3: 1.0, 4: 0.8}
MEDIA_TIER_SPEED = {1: 2.5, 2: 1.0, 3: 0.4}


@dataclass
class CascadeOutput:
    company: str
    ticker: str

    # core signals
    price_impact_day1_pct: float
    price_impact_30d_pct: float
    sector_spillover_delta_pct: float

    # regulatory
    regulatory_fine_p50_eur: float
    enforcement_probability: float

    # legal
    class_action_exposure_usd: float

    # reputation
    reputational_cost_score: float   # 0.0-1.0

    # composite
    disclosure_impact_score: float   # 0.0-100.0 — the headline number
    signal: str                      # STRONG_SHORT / SHORT / NEUTRAL / LONG
    confidence: float                # 0.0-1.0

    def summary(self) -> str:
        lines = [
            f"  company              {self.company} ({self.ticker or 'unlisted'})",
            f"  signal               {self.signal}  (confidence {self.confidence:.0%})",
            f"  impact score         {self.disclosure_impact_score:.1f}/100",
            f"  price day-1 est.     {self.price_impact_day1_pct:+.2f}%",
            f"  price 30-day est.    {self.price_impact_30d_pct:+.2f}%",
            f"  sector spillover     {self.sector_spillover_delta_pct:+.2f}%",
            f"  fine P50             €{self.regulatory_fine_p50_eur:,.0f}",
            f"  enforcement prob.    {self.enforcement_probability:.0%}",
            f"  class action exp.    ${self.class_action_exposure_usd:,.0f}",
            f"  reputational cost    {self.reputational_cost_score:.2f}/1.0",
        ]
        return "\n".join(lines)


def compute(p: DisclosureParams) -> CascadeOutput:
    # --- layer 1: finding severity composite ---
    children_mult = 1.8 if p.children_data_flag else 1.0
    china_mult = JURISDICTION_RISK.get(p.controller_jurisdiction, 1.0)
    if p.chinese_entity_flag:
        china_mult = max(china_mult, 1.6)

    severity_composite = (
        p.severity_score
        * p.evidence_strength
        * p.data_category_sensitivity
        * children_mult
        * (1.3 if p.finding_novelty_flag else 1.0)
        * (1.2 if p.third_country_transfer_flag else 1.0)
    )

    # --- layer 2: regulatory pressure ---
    dpa_mult = DPA_TIER_MULTIPLIER.get(p.lead_dpa_tier, 1.0)
    prior_recidivism = 1.0 + (p.prior_fine_count * 0.15)
    noyb_accel = 0.6 if p.noyb_complaint_preexisting else 1.0  # shortens timeline
    bcc_pressure = 1.0 + (p.bcc_regulator_count * 0.08)
    edpb_mult = 1.35 if p.edpb_involvement_flag else 1.0
    dsa_mult = 1.2 if p.dsa_investigation_overlap else 1.0

    enforcement_probability = min(0.95, (
        0.25
        * dpa_mult
        * prior_recidivism
        * bcc_pressure
        * edpb_mult
        * dsa_mult
        * p.public_disclosure_credibility
        * (1.0 - noyb_accel * 0.1)
    ))

    regulatory_fine_p50 = (
        p.fine_ceiling_eur
        * enforcement_probability
        * prior_recidivism
        * p.eu_revenue_fraction
        * dpa_mult
    )

    # --- layer 3: corporate response dampeners ---
    response_dampener = 1.0
    if p.dpo_response_time_days > 0 and p.dpo_response_time_days <= 3:
        response_dampener *= 0.7   # fast DPO response = less media
    if p.bug_bounty_program_exists:
        response_dampener *= 0.85
    if p.insurance_cybersec_coverage:
        response_dampener *= 0.9
    if p.prior_regulatory_settlement:
        response_dampener *= 1.1   # pattern of settling = market expects fine

    # --- layer 4: market signal ---
    media_mult = MEDIA_TIER_SPEED.get(p.media_outlet_tier, 1.0)
    media_speed_factor = max(0.3, 1.0 - (p.media_pickup_speed_hours / 96))

    # day-1 impact: driven by severity + media speed + short interest + iv
    price_impact_day1 = -(
        severity_composite * 0.004
        * china_mult
        * media_speed_factor
        * media_mult
        * (1.0 + p.short_interest_pct * 2.0)
        * (p.options_iv_current / 0.25)
        * response_dampener
    )
    price_impact_day1 = max(-0.25, price_impact_day1)  # cap at -25%

    # 30-day: driven by fine probability + analyst + eu revenue
    analyst_factor = min(2.0, p.analyst_coverage_count / 10)
    price_impact_30d = -(
        enforcement_probability
        * (regulatory_fine_p50 / max(1, p.market_cap_usd * 0.134))  # fine/mcap scaled
        * analyst_factor
        * (1.0 + (0.5 if p.congressional_mention_flag else 0.0))
        * (1.0 + (0.3 if p.whistleblower_corroboration else 0.0))
        * response_dampener
        * 8.0
    )
    price_impact_30d = max(-0.40, price_impact_30d)

    # sector spillover
    sector_spillover = (
        price_impact_day1
        * p.sector_contagion_coefficient
        * p.competitor_stock_correlation
        * (1.5 if p.index_membership else 0.8)
    )

    # class action (US empirical: 2-8% of mcap)
    class_action_low = p.market_cap_usd * 0.02
    class_action_high = p.market_cap_usd * 0.08
    class_action_exposure = (
        class_action_low + (class_action_high - class_action_low) * p.settlement_probability_prior
    ) * (1.0 / max(1, p.class_action_filing_speed_days / 7))

    # reputational cost: 0-1 score
    reputational_cost = min(1.0, (
        severity_composite * 0.05
        * (1.0 + p.social_media_velocity_tph * 0.01)
        * (1.5 if p.reddit_wsb_mention_flag else 1.0)
        * p.eu_revenue_fraction
    ))

    # --- composite disclosure impact score (0-100) ---
    impact_score = min(100.0, (
        abs(price_impact_day1) * 200
        + enforcement_probability * 20
        + severity_composite * 0.5
        + (china_mult - 1.0) * 15
        + p.children_data_flag * 10
    ))

    # signal
    if impact_score >= 65:
        signal = "STRONG_SHORT"
    elif impact_score >= 40:
        signal = "SHORT"
    elif impact_score >= 20:
        signal = "WATCH"
    else:
        signal = "NEUTRAL"

    confidence = min(0.95, p.evidence_strength * p.public_disclosure_credibility * (0.5 + enforcement_probability * 0.5))

    return CascadeOutput(
        company=p.company,
        ticker=p.ticker or "?",
        price_impact_day1_pct=price_impact_day1 * 100,
        price_impact_30d_pct=price_impact_30d * 100,
        sector_spillover_delta_pct=sector_spillover * 100,
        regulatory_fine_p50_eur=regulatory_fine_p50,
        enforcement_probability=enforcement_probability,
        class_action_exposure_usd=class_action_exposure,
        reputational_cost_score=reputational_cost,
        disclosure_impact_score=impact_score,
        signal=signal,
        confidence=confidence,
    )
