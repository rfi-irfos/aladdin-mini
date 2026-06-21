from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DisclosureParams:
    """50-parameter causality model: security disclosure → market impact.
    Designed by Brennan Bell (RFI-IRFOS Head of Model Safety & Welfare).
    """

    company: str
    ticker: Optional[str] = None

    # --- LAYER 1: Finding Characteristics ---
    severity_score: float = 0.0          # weighted: CRITICAL=10, HIGH=5, MEDIUM=2, LOW=1
    finding_count_critical: int = 0
    finding_count_high: int = 0
    gdpr_article_tier: int = 1           # 1=Art.9 > 2=Art.6 > 3=Art.13 > 4=Art.32
    data_category_sensitivity: float = 0.4  # health=1.0 biometric=0.9 financial=0.8 location=0.6 behavioral=0.4
    finding_novelty_flag: int = 0        # 1 if finding type never appeared in prior DPA decisions
    evidence_strength: float = 1.0       # 0.0-1.0: smali class count / proto name / endpoint URL
    chinese_entity_flag: int = 0         # 1 if NSL/DSL applicable (PDD, ByteDance, Huawei)
    third_country_transfer_flag: int = 0 # 1 if inadequate transfer mechanism confirmed
    children_data_flag: int = 0          # 1 if COPPA/GDPR Art.8 applies (multiplier ×1.8)

    # --- LAYER 2: Regulatory Exposure ---
    lead_dpa_tier: int = 3               # 1=DPC/CNPD 2=BayLDA 3=DSB 4=other
    prior_fine_count: int = 0
    prior_fine_magnitude_eur: float = 0.0
    fine_ceiling_eur: float = 0.0        # 4% of global annual turnover
    bcc_regulator_count: int = 0
    edpb_involvement_flag: int = 0
    dsa_investigation_overlap: int = 0
    noyb_complaint_preexisting: int = 0
    days_to_disclosure: int = 90
    public_disclosure_credibility: float = 0.7  # researcher reputation 0.0-1.0

    # --- LAYER 3: Corporate Response Dynamics ---
    dpo_response_time_days: float = 0.0
    bug_bounty_program_exists: int = 0
    public_statement_speed_hours: float = 0.0
    legal_team_size_proxy: int = 0       # 1 if Big4 law firm retained
    remediation_cost_fraction: float = 0.01  # estimated fix cost / annual revenue
    insurance_cybersec_coverage: int = 0
    prior_regulatory_settlement: int = 0
    eu_revenue_fraction: float = 0.2
    ceo_public_statement_flag: int = 0
    controller_jurisdiction: str = "US"  # CN=highest / US=high / IE/LU=medium / DE=lower

    # --- LAYER 4: Market Signal Propagation ---
    market_cap_usd: float = 0.0
    beta_coefficient: float = 1.0
    short_interest_pct: float = 0.02
    options_iv_current: float = 0.25
    institutional_ownership_frac: float = 0.7
    index_membership: int = 0            # 1 if S&P500 / NASDAQ100 / DAX
    analyst_coverage_count: int = 10
    days_since_earnings: int = 45
    sector_contagion_coefficient: float = 0.2
    competitor_stock_correlation: float = 0.4

    # --- LAYER 5: Media & Social Velocity ---
    media_pickup_speed_hours: float = 48.0
    media_outlet_tier: int = 2           # 1=WSJ/Bloomberg/NYT 2=TechCrunch/Wired 3=blogs
    social_media_velocity_tph: float = 0.0  # tweets+posts/hour in first 6h
    reddit_wsb_mention_flag: int = 0
    analyst_downgrade_lag_days: float = 7.0
    class_action_filing_speed_days: float = 21.0
    congressional_mention_flag: int = 0
    whistleblower_corroboration: int = 0
    regulator_press_release_lag: float = 30.0
    settlement_probability_prior: float = 0.4
