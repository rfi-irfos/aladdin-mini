from aladdin import DisclosureParams, compute

params = DisclosureParams(
    company="PayPal",
    ticker="PYPL",

    # layer 1 — finding characteristics
    severity_score=10 * 3 + 5 * 2,   # C1 Chucker + C2 4x biometric + C3 Firebase + 2 HIGH
    finding_count_critical=3,
    finding_count_high=2,
    gdpr_article_tier=1,              # Art.9 biometric
    data_category_sensitivity=0.9,   # biometric
    finding_novelty_flag=1,           # Chucker in PSD2 payment processor = novel
    evidence_strength=1.0,            # 246 smali + 4,269 biometric smali — irrefutable
    chinese_entity_flag=0,
    third_country_transfer_flag=1,    # 4x US biometric processors, no adequacy
    children_data_flag=0,

    # layer 2 — regulatory
    lead_dpa_tier=1,                  # Irish DPC (PayPal EU HQ in Dublin)
    prior_fine_count=2,
    prior_fine_magnitude_eur=4_000_000,
    fine_ceiling_eur=2_800_000_000,   # 4% of ~$70B revenue
    bcc_regulator_count=4,            # DSB + CERT.at + DPC + BFDI
    edpb_involvement_flag=0,
    dsa_investigation_overlap=0,
    noyb_complaint_preexisting=1,     # noyb has active PayPal complaints
    days_to_disclosure=90,
    public_disclosure_credibility=0.85,

    # layer 3 — corporate response
    dpo_response_time_days=0,
    bug_bounty_program_exists=1,      # HackerOne program exists
    legal_team_size_proxy=1,
    remediation_cost_fraction=0.001,
    insurance_cybersec_coverage=1,
    prior_regulatory_settlement=1,
    eu_revenue_fraction=0.35,
    ceo_public_statement_flag=0,
    controller_jurisdiction="US",

    # layer 4 — market
    market_cap_usd=65_000_000_000,
    beta_coefficient=1.4,
    short_interest_pct=0.04,
    options_iv_current=0.38,
    institutional_ownership_frac=0.75,
    index_membership=1,               # NASDAQ100
    analyst_coverage_count=32,
    days_since_earnings=52,
    sector_contagion_coefficient=0.4, # fintech contagion
    competitor_stock_correlation=0.55,

    # layer 5 — media
    media_pickup_speed_hours=6.0,
    media_outlet_tier=1,              # Bloomberg / FT / WSJ cover PayPal
    social_media_velocity_tph=0,
    reddit_wsb_mention_flag=0,
    analyst_downgrade_lag_days=5.0,
    class_action_filing_speed_days=14.0,
    congressional_mention_flag=0,
    whistleblower_corroboration=0,
    regulator_press_release_lag=21.0,
    settlement_probability_prior=0.7,
)

if __name__ == "__main__":
    result = compute(params)
    print(result.summary())
