"""
MT5 bridge — connects Aladdin signal + SHS position system to AvaTrade MT5.
Requires: pip install MetaTrader5
MT5 terminal must be running (via Wine on Linux).

SHS rules enforced here:
  - TP always set. SL never set (mental only, stop-hunt-proof).
  - 33% cash reserve check before every order.
  - Stage 1: micro layers via add_layer()
  - Stage 3: killshot via fire_killshot()
  - Credo: sniper, not machine gun.
"""

from .model import CascadeOutput
from .shs import SHSState, SHSPosition, add_layer, fire_killshot

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

MAGIC = 20260621  # aladdin-mini order identifier


def connect() -> bool:
    if not MT5_AVAILABLE:
        print("[mt5] MetaTrader5 not installed. Run: pip install MetaTrader5")
        return False
    if not mt5.initialize():
        print(f"[mt5] initialize() failed: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    acc = mt5.account_info()
    print(f"[mt5] connected: {info.name} build {info.build}")
    print(f"[mt5] account: {acc.login} | balance: {acc.balance:.2f} {acc.currency} | hedge: {acc.margin_mode == 0}")
    return True


def disconnect():
    if MT5_AVAILABLE:
        mt5.shutdown()


def _current_price(symbol: str, direction: str) -> float:
    tick = mt5.symbol_info_tick(symbol)
    return tick.ask if direction == "BUY" else tick.bid


def _send_order(symbol: str, direction: str, lots: float, tp: float, comment: str, dry_run: bool) -> dict:
    price = _current_price(symbol, direction) if not dry_run else tp

    if dry_run:
        print(f"  [dry] {direction} {lots} lot {symbol} @ ~{price:.5f}  TP {tp:.5f}  SL none (mental)")
        return {"status": "dry_run", "direction": direction, "lots": lots, "tp": tp}

    if not MT5_AVAILABLE:
        return {"status": "error", "reason": "MT5 not available"}

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lots,
        "type":         order_type,
        "price":        price,
        "tp":           tp,
        "sl":           0.0,       # SHS rule: no hard SL. ever.
        "deviation":    20,
        "magic":        MAGIC,
        "comment":      comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(request)
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return {"status": "error", "retcode": res.retcode, "comment": res.comment}
    return {"status": "filled", "order": res.order, "price": res.price, "volume": res.volume}


def shs_add_layer(state: SHSState, dry_run: bool = True) -> dict:
    """Add next stage-1 micro layer via SHS logic."""
    if not MT5_AVAILABLE and not dry_run:
        return {"status": "error", "reason": "MT5 not available"}

    price = _current_price(state.symbol, state.direction) if not dry_run else 0.0
    if dry_run:
        # use a dummy price for dry run
        price = 157.0 if "JPY" in state.symbol else 1.0

    pos = add_layer(state, price)
    if pos is None:
        if state.at_stage1_limit():
            return {"status": "skip", "reason": "stage 1 complete — wait for daily/weekly confirmation"}
        if not state.cash_ok():
            return {"status": "blocked", "reason": "cash reserve below 33% — no new positions"}
        return {"status": "skip", "reason": "unknown"}

    result = _send_order(
        symbol=state.symbol,
        direction=pos.direction,
        lots=pos.lots,
        tp=pos.tp_price,
        comment=f"aladdin SHS {pos.note}",
        dry_run=dry_run,
    )
    result["stage"] = state.stage
    result["total_lots"] = state.total_lots
    return result


def shs_killshot(state: SHSState, dry_run: bool = True) -> dict:
    """Fire stage-3 killshot. Only call after daily + weekly confirmation."""
    if state.stage != 2:
        return {"status": "skip", "reason": f"not ready for killshot (stage={state.stage}, need stage 2)"}

    if not MT5_AVAILABLE and not dry_run:
        return {"status": "error", "reason": "MT5 not available"}

    price = _current_price(state.symbol, state.direction) if not dry_run else 0.0
    if dry_run:
        price = 156.5 if "JPY" in state.symbol else 1.0

    pos = fire_killshot(state, price)
    if pos is None:
        return {"status": "blocked", "reason": "cash reserve below 33%"}

    print(f"[shs] KILLSHOT — sniper, not machine gun.")
    result = _send_order(
        symbol=state.symbol,
        direction=pos.direction,
        lots=pos.lots,
        tp=pos.tp_price,
        comment="aladdin SHS killshot",
        dry_run=dry_run,
    )
    result["stage"] = 3
    result["total_lots"] = state.total_lots
    return result


def aladdin_signal_to_shs(result: CascadeOutput, symbol: str) -> tuple:
    """Map Aladdin disclosure signal → SHS direction for correlated equity/index."""
    signal_map = {
        "STRONG_SHORT": "SELL",
        "SHORT":        "SELL",
        "WATCH":        None,
        "NEUTRAL":      None,
    }
    direction = signal_map.get(result.signal)
    return direction, result.confidence
