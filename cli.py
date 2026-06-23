#!/usr/bin/env python3
"""
aladdin-mini CLI

Usage:
  python cli.py examples/paypal_2026.py                          # compute + governance
  python cli.py examples/paypal_2026.py --calibrate              # + Bayesian calibration
  python cli.py examples/paypal_2026.py --counterfactual         # + causal analysis
  python cli.py examples/paypal_2026.py --pe-ratio 31            # + Warren Buffett check
  python cli.py examples/paypal_2026.py --write-signal           # write signal file for MT5 EA
  python cli.py examples/paypal_2026.py --write-signal /path/to/MQL5/Files/aladdin_signal.txt
  python cli.py examples/paypal_2026.py --mt5 SQQQ               # dry-run MT5 order
  python cli.py examples/paypal_2026.py --mt5 SQQQ --live        # live order
  python cli.py optimize                                          # run GA weight optimizer
  python cli.py optimize --generations 1000                       # more thorough run
"""

import sys
import importlib.util
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def load_example(path: str):
    spec = importlib.util.spec_from_file_location("example", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.params


def run_signal(args):
    from aladdin import compute
    from aladdin.governance import apply_gates
    from aladdin.bayesian_calibrator import calibrate

    params = load_example(args.example)
    result = compute(params)
    gov = apply_gates(params, result)

    print("\naladdin-mini — disclosure impact signal")
    print("=" * 50)
    if gov.overridden:
        print(f"  signal (raw)         {gov.original_signal}")
        print(f"  signal (governed)    {gov.final_signal}  ← gates: {', '.join(gov.gates_triggered)}")
        for r in gov.rationale:
            print(f"    {r}")
    else:
        print(result.summary())

    if not gov.overridden:
        print()

    if args.calibrate:
        cal = calibrate(params, result.enforcement_probability)
        print()
        print("  bayesian calibration (auto-bayesian / pgmpy)")
        print(f"  ──────────────────────────────────────────")
        if cal.available:
            print(f"  model enforcement prob     {cal.original_enforcement_prob:.1%}")
            print(f"  bayesian posterior         {cal.bayesian_posterior:.1%}")
            print(f"  calibrated (blend {cal.blend_weight:.0%})     {cal.calibrated_enforcement_prob:.1%}")
            print(f"  n historical outcomes      {cal.n_historical}")
            print(f"  feature bins               dpa={cal.dpa_tier_bin} sev={cal.severity_bin} prior={cal.prior_fine_bin}")
        else:
            print("  pgmpy not available — run: pip install pgmpy")

    print()

    # --- Warren Buffett fundamentals check ---
    buffett_tier = "unknown"
    if args.pe_ratio is not None:
        from aladdin.fundamentals import check_fundamentals, apply_buffett_filter
        fs = check_fundamentals(
            nas100_pe=args.pe_ratio,
            buffett_indicator_pct=args.buffett_indicator,
        )
        buffett_tier = fs.valuation_tier
        print()
        print(fs.summary())
        print()

        # Optionally adjust the final signal
        adjusted = apply_buffett_filter(gov.final_signal, fs)
        if adjusted != gov.final_signal:
            print(f"  [buffett filter] signal adjusted: {gov.final_signal} → {adjusted}")
            gov.final_signal = adjusted
            result.signal = adjusted

    if args.counterfactual:
        from aladdin.counterfactual import run_counterfactuals
        print()
        print("  [fitting SCM on 500 synthetic samples — causal-perception / LinearANM]")
        cf_report = run_counterfactuals(params)
        print()
        print(cf_report.summary())
        print()

    # --- Write signal file for MT5 EA ---
    if args.write_signal is not None:
        from aladdin.mt5_bridge import write_signal_file
        signal_path = args.write_signal if args.write_signal else "aladdin_signal.txt"
        company_name = getattr(params, "company", "")
        result.signal = gov.final_signal
        write_signal_file(result, signal_path, buffett_tier=buffett_tier, company=company_name)

    if args.mt5:
        from aladdin.mt5_bridge import connect, disconnect
        connected = connect()
        if connected or not args.live:
            result.signal = gov.final_signal
            from aladdin.shs import SHSState
            state = SHSState(
                symbol=args.mt5,
                direction="SELL" if result.signal in ("STRONG_SHORT", "SHORT") else None,
                total_equity=100_000,  # placeholder
            )
            from aladdin.mt5_bridge import shs_add_layer
            out = shs_add_layer(state, dry_run=not args.live)
            print(f"[mt5] result: {out}")
            if connected:
                disconnect()


def run_optimizer(args):
    from aladdin.genetic_optimizer import optimize
    generations = args.generations if hasattr(args, "generations") else 200
    print(f"\naladdin-mini — genetic weight optimizer")
    print(f"  running {generations} generations (SantanderAI/genetic-algorithm, Apache 2.0)")
    print("  ──────────────────────────────────────────")
    weights = optimize(generations=generations)
    print(weights.summary())
    print()
    print("  to apply: update model.py constants with the values above.")


def main():
    parser = argparse.ArgumentParser(description="aladdin-mini: disclosure → market signal")
    # default: positional example file
    parser.add_argument("example", nargs="?", help="path to example file, or 'optimize'")
    parser.add_argument("--mt5", metavar="SYMBOL", help="MT5 symbol to trade")
    parser.add_argument("--live", action="store_true", help="place real order (default: dry run)")
    parser.add_argument("--calibrate", action="store_true",
                        help="apply Bayesian calibration (auto-bayesian/pgmpy)")
    parser.add_argument("--counterfactual", action="store_true",
                        help="run causal counterfactual analysis (causal-perception/LinearANM)")
    parser.add_argument("--pe-ratio", type=float, metavar="PE",
                        help="NAS100 trailing P/E ratio for Warren Buffett valuation check")
    parser.add_argument("--buffett-indicator", type=float, metavar="PCT",
                        help="Buffett indicator (Wilshire5000/GDP %%, e.g. 200 for 200%%)")
    parser.add_argument("--write-signal", nargs="?", const="aladdin_signal.txt",
                        metavar="PATH",
                        help="write MT5 signal file (default: aladdin_signal.txt)")
    parser.add_argument("--generations", type=int, default=200,
                        help="(with optimize) GA generations")

    args = parser.parse_args()

    if args.example == "optimize":
        run_optimizer(args)
        return

    if not args.example:
        parser.print_help()
        return

    run_signal(args)


if __name__ == "__main__":
    main()
