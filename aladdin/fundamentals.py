"""
Aladdin Mini — fundamentals layer (Warren Buffett valuation check).

Before placing any trade, aladdin-mini asks: "what would Warren Buffett say?"
The P/E ratio and intrinsic value are the GRANDER, longer-term signal than a
chart spike. A disclosure-driven SHORT is confirmed if the market is already
priced for perfection; it is tempered if stocks are genuinely cheap.

Two metrics:
  1. NAS100 trailing P/E ratio (most relevant for SQQQ/TQQQ trades)
  2. Buffett Indicator: total US market cap / US GDP (Wilshire 5000 / GDP %)

Historical anchors (NAS100 P/E):
  Tech bear trough 2002: ~20   (post dot-com crash)
  GFC trough 2009:        ~14  (generational cheap)
  Post-GFC recovery 2013: ~22
  Pre-pandemic 2019:       ~26
  Covid peak 2021:         ~38
  Rate-hike trough 2022:   ~22
  Current 2026-Q2:         ~31  (elevated but not 2021 extreme)

Buffett Indicator (market cap / GDP %):
  Historical fair value: ~100%
  Current 2026-Q2:       ~200%  (extremely elevated, Buffett himself is holding cash)
"""

from __future__ import annotations

from dataclasses import dataclass


# Historical P/E percentile anchors for NAS100
_PE_CHEAP      = 18.0   # below = genuinely cheap, shorts face strong mean-reversion
_PE_FAIR_LOW   = 22.0
_PE_FAIR_HIGH  = 28.0
_PE_ELEVATED   = 35.0   # above = priced for perfection
_PE_BUBBLE     = 45.0   # above = dot-com territory


@dataclass
class FundamentalsSignal:
    nas100_pe: float
    buffett_indicator_pct: float | None  # Wilshire5000/GDP %, None if not provided
    valuation_tier: str   # "cheap" | "fair" | "elevated" | "bubble"
    buffett_verdict: str  # "LONG_FAVORABLE" | "NEUTRAL" | "SHORT_FAVORABLE"
    short_signal_adjustment: int   # -1 = weaken short, 0 = no change, +1 = strengthen
    narrative: str

    def summary(self) -> str:
        lines = [
            "  fundamentals check (Warren Buffett layer)",
            f"  NAS100 trailing P/E:    {self.nas100_pe:.1f}  ({self.valuation_tier})",
        ]
        if self.buffett_indicator_pct is not None:
            lines.append(f"  Buffett indicator:      {self.buffett_indicator_pct:.0f}%  (fair value ≈ 100%)")
        adj_str = {-1: "weaken (market may be cheap enough to absorb)", 0: "no change", +1: "strengthen (market priced for perfection)"}.get(self.short_signal_adjustment, "no change")
        lines.append(f"  short signal adj:       {adj_str}")
        lines.append(f"  verdict:                {self.buffett_verdict}")
        lines.append(f"  narrative:              {self.narrative}")
        return "\n".join(lines)


def check_fundamentals(
    nas100_pe: float,
    buffett_indicator_pct: float | None = None,
) -> FundamentalsSignal:
    """Evaluate NAS100 valuation vs. disclosure-driven short signal.

    Args:
        nas100_pe: NAS100 trailing 12-month P/E ratio.
        buffett_indicator_pct: Wilshire 5000 market cap / US GDP * 100.
            Optional. If provided, adds a second overvaluation signal.

    Returns:
        FundamentalsSignal with verdict and signal adjustment.
    """
    # --- Determine valuation tier ---
    if nas100_pe < _PE_CHEAP:
        tier = "cheap"
    elif nas100_pe < _PE_FAIR_HIGH:
        tier = "fair"
    elif nas100_pe < _PE_BUBBLE:
        tier = "elevated"
    else:
        tier = "bubble"

    # --- Buffett indicator cross-check ---
    buffett_overvalued = False
    if buffett_indicator_pct is not None:
        buffett_overvalued = buffett_indicator_pct > 150.0

    # --- Determine signal adjustment for disclosure-driven SHORTS ---
    #
    # The logic: a privacy/data scandal causes a stock to drop. The magnitude
    # and recovery speed depend on valuation. If the market is stretched, the
    # stock has farther to fall and takes longer to recover — the SHORT is
    # more powerful. If the market is genuinely cheap, the same scandal may
    # be a "buy the dip" opportunity for long-term holders → shorter-lived
    # short window.
    #
    if tier == "bubble":
        adj = +1
        verdict = "SHORT_FAVORABLE"
        narrative = (
            "Buffett would say: 'When the tide goes out, you see who's swimming naked. "
            "At P/E {pe:.0f}, this market is priced for a world where nothing goes wrong. "
            "A disclosure event is exactly what strips away that optimism.' "
            "Short confirmed. Take the full SHS stage 1."
        ).format(pe=nas100_pe)

    elif tier == "elevated":
        adj = +1 if buffett_overvalued else 0
        verdict = "SHORT_FAVORABLE"
        narrative = (
            "Buffett would say: 'P/E {pe:.0f} is not cheap. You're not getting a bargain "
            "here. A bad disclosure is a reminder that growth expectations were priced in — "
            "and the market will reprice them. SHORT is reasonable, but size carefully.'"
        ).format(pe=nas100_pe)

    elif tier == "fair":
        adj = 0
        verdict = "NEUTRAL"
        narrative = (
            "Buffett would say: 'At P/E {pe:.0f} you're paying a fair price for fair businesses. "
            "A disclosure event will still hurt the stock short-term — the signal stands. "
            "But don't swing for the fences; exits should be tighter in a fair-valued market.'"
        ).format(pe=nas100_pe)

    else:  # cheap
        adj = -1
        verdict = "LONG_FAVORABLE"
        narrative = (
            "Buffett would say: 'P/E {pe:.0f}? This is the kind of market I like. "
            "Yes, this company made a mistake. But at these prices, institutions will buy "
            "the dip before you exit. Temper the short — take profits early or wait for a "
            "truly egregious case before going heavy.'"
        ).format(pe=nas100_pe)

    return FundamentalsSignal(
        nas100_pe=nas100_pe,
        buffett_indicator_pct=buffett_indicator_pct,
        valuation_tier=tier,
        buffett_verdict=verdict,
        short_signal_adjustment=adj,
        narrative=narrative,
    )


def apply_buffett_filter(signal: str, fs: FundamentalsSignal) -> str:
    """Optionally downgrade or strengthen a signal based on fundamentals.

    Only downgrades STRONG_SHORT → SHORT when market is genuinely cheap.
    Never overrides a NEUTRAL signal (human decides when to go long).

    Args:
        signal: "STRONG_SHORT" | "SHORT" | "WATCH" | "NEUTRAL"
        fs: FundamentalsSignal from check_fundamentals()

    Returns:
        Potentially adjusted signal string.
    """
    if fs.short_signal_adjustment == -1:
        # cheap market — downgrade STRONG_SHORT to SHORT
        if signal == "STRONG_SHORT":
            return "SHORT"
    # +1 or 0: no downgrade
    return signal
