"""
SHS — Simeon Hedge System
"sniper, not machine gun."

Three-stage position building system:
  Stage 1 — micro scouting (linear layering against the move)
  Stage 2 — wait for daily/weekly confirmation (no new lots)
  Stage 3 — killshot (1 lot: simultaneous stop-loss AND profit maximizer)

Rules:
  - TP always set. SL never set (mental only — stop-hunt-proof).
  - 33% cash reserve ALWAYS. Non-negotiable.
  - Entry signal: 4H RSI minimum. Confirm on daily + weekly before stage 3.
  - Preferred assets: USDJPY, USDHUF, NAS100
  - Credo: sniper, not machine gun.
"""

from dataclasses import dataclass, field
from typing import Optional


PREFERRED_ASSETS = ["USDJPY", "USDHUF", "NAS100", "US100"]

# linear layer increments (not martingale — never doubles)
STAGE1_INCREMENTS = [0.01, 0.10, 0.25, 0.50]
STAGE3_KILLSHOT_LOT = 1.0

CASH_RESERVE_MIN = 0.33   # 33% cash reserve — hard floor, never touch


@dataclass
class SHSPosition:
    symbol: str
    direction: str           # "BUY" or "SELL"
    lots: float
    entry_price: float
    tp_price: float
    sl_price: float = 0.0   # always 0 — mental SL only, never on chart
    stage: int = 1
    note: str = ""


@dataclass
class SHSState:
    symbol: str
    direction: str
    stage: int = 1
    positions: list = field(default_factory=list)
    total_lots: float = 0.0
    account_balance: float = 0.0
    cash_reserve_pct: float = CASH_RESERVE_MIN

    def at_stage1_limit(self) -> bool:
        return self.total_lots >= STAGE1_INCREMENTS[-1]

    def cash_ok(self) -> bool:
        used = self.total_lots * 1000  # rough margin proxy
        return (self.account_balance - used) / self.account_balance >= CASH_RESERVE_MIN

    def summary(self) -> str:
        lines = [
            f"  symbol       {self.symbol}  {self.direction}",
            f"  stage        {self.stage}",
            f"  total lots   {self.total_lots:.2f}",
            f"  positions    {len(self.positions)}",
            f"  cash ok      {'yes' if self.cash_ok() else 'NO — below 33% reserve'}",
        ]
        for i, p in enumerate(self.positions):
            tag = "KILLSHOT" if p.stage == 3 else f"layer {i+1}"
            lines.append(f"    [{tag}] {p.lots} lot @ {p.entry_price:.5f}  TP {p.tp_price:.5f}")
        return "\n".join(lines)


def next_layer_lot(state: SHSState) -> Optional[float]:
    """Returns next lot size for stage 1 layering, or None if limit reached."""
    n = len([p for p in state.positions if p.stage == 1])
    if n >= len(STAGE1_INCREMENTS):
        return None
    return STAGE1_INCREMENTS[n]


def tp_price(entry: float, direction: str, symbol: str, stage: int) -> float:
    """
    TP distance heuristic by asset and stage.
    Stage 3 killshot uses tighter TP — it just needs to tip into profit.
    Tune per asset based on ATR / spread table from AvaTrade.
    """
    pips = {
        "USDJPY":  {"s1": 0.80,  "s3": 0.25},
        "USDHUF":  {"s1": 5.00,  "s3": 1.50},
        "NAS100":  {"s1": 25.0,  "s3": 8.0},
        "US100":   {"s1": 25.0,  "s3": 8.0},
    }.get(symbol, {"s1": 1.0, "s3": 0.3})

    distance = pips["s3"] if stage == 3 else pips["s1"]
    return entry + distance if direction == "BUY" else entry - distance


def add_layer(state: SHSState, current_price: float) -> Optional[SHSPosition]:
    """
    Add next stage-1 micro layer. Returns position to open, or None if blocked.
    Never adds if cash reserve would drop below 33%.
    """
    if state.stage != 1:
        return None

    lot = next_layer_lot(state)
    if lot is None:
        return None

    if not state.cash_ok():
        return None  # 33% floor — hard block

    pos = SHSPosition(
        symbol=state.symbol,
        direction=state.direction,
        lots=lot,
        entry_price=current_price,
        tp_price=tp_price(current_price, state.direction, state.symbol, stage=1),
        sl_price=0.0,   # mental SL only. never on chart.
        stage=1,
        note=f"layer {len(state.positions) + 1} of {len(STAGE1_INCREMENTS)}",
    )
    state.positions.append(pos)
    state.total_lots += lot

    if state.at_stage1_limit():
        state.stage = 2   # auto-advance: wait for daily/weekly confirmation

    return pos


def fire_killshot(state: SHSState, current_price: float) -> Optional[SHSPosition]:
    """
    Stage 3: fire the 1-lot killshot.
    Only valid after daily + weekly chart confirmation (caller's responsibility).
    The killshot is simultaneously the SL (accepts total stack loss if wrong)
    and the profit maximizer (carries the reversal if right).
    Credo: sniper, not machine gun.
    """
    if state.stage != 2:
        return None

    if not state.cash_ok():
        return None

    pos = SHSPosition(
        symbol=state.symbol,
        direction=state.direction,
        lots=STAGE3_KILLSHOT_LOT,
        entry_price=current_price,
        tp_price=tp_price(current_price, state.direction, state.symbol, stage=3),
        sl_price=0.0,   # mental SL only.
        stage=3,
        note="killshot — sniper, not machine gun.",
    )
    state.positions.append(pos)
    state.total_lots += STAGE3_KILLSHOT_LOT
    state.stage = 3

    return pos


def accept_loss(state: SHSState) -> str:
    """
    Mental SL triggered. Close everything, reset.
    'Accept the loss, make nothing.' — SHS core rule.
    """
    summary = f"SHS: accepting loss on {len(state.positions)} positions ({state.total_lots:.2f} lots total)."
    state.positions.clear()
    state.total_lots = 0.0
    state.stage = 1
    return summary
