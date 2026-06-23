#!/usr/bin/env python3
"""
aladdin-mini CLI

Usage:
  python cli.py examples/paypal_2026.py              # compute + governance
  python cli.py examples/paypal_2026.py --calibrate  # + Bayesian calibration
  python cli.py examples/paypal_2026.py --mt5 PYPL   # dry-run MT5 order
  python cli.py examples/paypal_2026.py --mt5 PYPL --live  # live order
  python cli.py --optimize                            # run GA weight optimizer
  python cli.py --optimize --generations 1000         # more thorough run
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
    result_display = result
    if gov.overridden:
        # show original + override
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

    if args.mt5:
        from aladdin.mt5_bridge import connect, place_signal, disconnect
        connected = connect()
        if connected or not args.live:
            signal_to_use = gov.final_signal
            # patch result signal for MT5 bridge
            result.signal = signal_to_use
            out = place_signal(result, args.mt5, dry_run=not args.live)
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
    parser.add_argument("--generations", type=int, default=200,
                        help="(with --optimize) GA generations")

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
