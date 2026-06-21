from aladdin import DisclosureParams, compute

params = DisclosureParams(
    company="Snap Inc.",
    ticker="SNAP",

    # layer 1 — Fidelius E2E lie is highest novelty finding in series
    severity_score=10 * 1 + 5 * 6,
    finding_count_critical=1,
    finding_count_high=6,
    gdpr_article_tier=1,              # Art.9 biometric (facial recognition filters)
    data_category_sensitivity=0.7,
    finding_novelty_flag=1,           # Fidelius keys at Google = disappearing messages lie — novel globally
    evidence_strength=0.95,
    chinese_entity_flag=0,
    third_country_transfer_flag=1,
    children_data_flag=1,             # Snapchat has under-18 users, ×1.8

    # layer 2
    lead_dpa_tier=1,                  # Irish DPC (Snap EU Dublin)
    prior_fine_count=3,
    prior_fine_magnitude_eur=4_900_000,  # ICO 2023 £12.7M
    fine_ceiling_eur=480_000_000,     # 4% of ~$4.6B revenue
    bcc_regulator_count=5,            # ICO + EDPB + DSB + DPC + CERT.at
    edpb_involvement_flag=1,          # children's data = EDPB task force
    dsa_investigation_overlap=1,
    noyb_complaint_preexisting=0,
    days_to_disclosure=90,
    public_disclosure_credibility=0.85,

    # layer 3
    dpo_response_time_days=0,
    bug_bounty_program_exists=1,
    legal_team_size_proxy=1,
    remediation_cost_fraction=0.02,
    insurance_cybersec_coverage=1,
    prior_regulatory_settlement=1,
    eu_revenue_fraction=0.25,
    ceo_public_statement_flag=0,
    controller_jurisdiction="US",

    # layer 4
    market_cap_usd=16_500_000_000,
    beta_coefficient=1.8,
    short_interest_pct=0.09,          # high short interest
    options_iv_current=0.55,
    institutional_ownership_frac=0.6,
    index_membership=0,
    analyst_coverage_count=28,
    days_since_earnings=30,
    sector_contagion_coefficient=0.5, # social media contagion (Meta, TikTok)
    competitor_stock_correlation=0.62,

    # layer 5
    media_pickup_speed_hours=3.0,     # "disappearing messages = lie" is a headline
    media_outlet_tier=1,
    social_media_velocity_tph=0,
    reddit_wsb_mention_flag=1,
    analyst_downgrade_lag_days=4.0,
    class_action_filing_speed_days=7.0,
    congressional_mention_flag=1,     # children's data + E2E deception
    whistleblower_corroboration=0,
    regulator_press_release_lag=14.0,
    settlement_probability_prior=0.65,
)

if __name__ == "__main__":
    result = compute(params)
    print(result.summary())
