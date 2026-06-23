"""
Aladdin Mini — mechanical hard gates for disclosure signals.

Inspired by Santander AI Lab's mech-gov-framework (Apache 2.0).
github.com/rfi-irfos/mech-gov-framework (fork)

Gates are evaluated AFTER compute() but BEFORE the signal is returned to the
caller. First matching gate wins. Gate actions: BLOCK (→ WATCH), DOWNGRADE
(one step down), UPGRADE (one step up), WARN (no signal change).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .params import DisclosureParams
from .model import CascadeOutput

_SIGNAL_ORDER = ["NEUTRAL", "WATCH", "SHORT", "STRONG_SHORT"]


def _step_down(signal: str) -> str:
    idx = _SIGNAL_ORDER.index(signal) if signal in _SIGNAL_ORDER else 1
    return _SIGNAL_ORDER[max(0, idx - 1)]


def _step_up(signal: str) -> str:
    idx = _SIGNAL_ORDER.index(signal) if signal in _SIGNAL_ORDER else 1
    return _SIGNAL_ORDER[min(len(_SIGNAL_ORDER) - 1, idx + 1)]


@dataclass
class HardGate:
    gate_id: str
    description: str
    condition: Callable[[DisclosureParams, CascadeOutput], bool]
    action: str          # BLOCK | DOWNGRADE | UPGRADE | WARN
    rationale: str       # may contain {val} for one formatted value


@dataclass
class GovernanceResult:
    original_signal: str
    final_signal: str
    gates_triggered: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    overridden: bool = False


_GATES: list[HardGate] = [
    HardGate(
        gate_id="A1",
        description="Evidence too weak for SHORT/STRONG_SHORT",
        condition=lambda p, o: (
            p.evidence_strength < 0.5 and o.signal in ("SHORT", "STRONG_SHORT")
        ),
        action="BLOCK",
        rationale=(
            "Gate A1: evidence_strength {val:.2f} < 0.5. Insufficient to support a SHORT "
            "signal under SHS sniper doctrine — signal downgraded to WATCH."
        ),
    ),
    HardGate(
        gate_id="A2",
        description="Market cap unknown — position sizing impossible",
        condition=lambda p, o: (
            p.market_cap_usd == 0 and o.signal in ("SHORT", "STRONG_SHORT")
        ),
        action="BLOCK",
        rationale=(
            "Gate A2: market_cap_usd = 0. Cannot compute fine/cap ratio or size any "
            "SHS layer. Signal downgraded to WATCH."
        ),
    ),
    HardGate(
        gate_id="A3",
        description="Low researcher credibility — STRONG_SHORT blocked",
        condition=lambda p, o: (
            p.public_disclosure_credibility < 0.4 and o.signal == "STRONG_SHORT"
        ),
        action="DOWNGRADE",
        rationale=(
            "Gate A3: public_disclosure_credibility {val:.2f} < 0.4. STRONG_SHORT requires "
            "credible, verifiable disclosure. Downgraded to SHORT."
        ),
    ),
    HardGate(
        gate_id="A4",
        description="Children data + critical severity → floor at WATCH",
        condition=lambda p, o: (
            bool(p.children_data_flag) and p.severity_score >= 8 and o.signal == "NEUTRAL"
        ),
        action="UPGRADE",
        rationale=(
            "Gate A4: GDPR Art.8/COPPA applies + severity {val:.1f}. "
            "Regulatory floor: NEUTRAL → WATCH."
        ),
    ),
    HardGate(
        gate_id="A5",
        description="Chinese entity — NSL enforcement pathway uncertain",
        condition=lambda p, o: (
            bool(p.chinese_entity_flag) and o.signal == "STRONG_SHORT"
        ),
        action="DOWNGRADE",
        rationale=(
            "Gate A5: Chinese entity (NSL/DSL applicable). EU enforcement against "
            "PRC-domiciled companies historically stalls. STRONG_SHORT → SHORT."
        ),
    ),
    HardGate(
        gate_id="A6",
        description="No fine ceiling set — regulatory math unreliable",
        condition=lambda p, o: (
            p.fine_ceiling_eur == 0 and o.signal == "STRONG_SHORT"
        ),
        action="DOWNGRADE",
        rationale=(
            "Gate A6: fine_ceiling_eur = 0 (turnover unknown). Regulatory fine estimate "
            "unreliable. STRONG_SHORT → SHORT."
        ),
    ),
]


def apply_gates(p: DisclosureParams, output: CascadeOutput) -> GovernanceResult:
    """Apply mechanical hard gates to a cascade output. First match wins."""
    signal = output.signal
    triggered_ids: list[str] = []
    triggered_rationale: list[str] = []

    for gate in _GATES:
        if not gate.condition(p, output):
            continue

        # format rationale with gate-specific value
        val_map = {
            "A1": p.evidence_strength,
            "A2": p.market_cap_usd,
            "A3": p.public_disclosure_credibility,
            "A4": p.severity_score,
            "A5": 0.0,
            "A6": p.fine_ceiling_eur,
        }
        val = val_map.get(gate.gate_id, 0.0)
        try:
            rationale_text = gate.rationale.format(val=val)
        except (KeyError, ValueError):
            rationale_text = gate.rationale

        triggered_ids.append(gate.gate_id)
        triggered_rationale.append(rationale_text)

        if gate.action == "BLOCK":
            signal = "WATCH"
        elif gate.action == "DOWNGRADE":
            signal = _step_down(signal)
        elif gate.action == "UPGRADE":
            signal = _step_up(signal)
        # WARN: no change

    return GovernanceResult(
        original_signal=output.signal,
        final_signal=signal,
        gates_triggered=triggered_ids,
        rationale=triggered_rationale,
        overridden=signal != output.signal,
    )
