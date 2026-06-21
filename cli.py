#!/usr/bin/env python3
"""
aladdin-mini CLI
Usage:
  python cli.py examples/paypal_2026.py              # compute + print signal
  python cli.py examples/paypal_2026.py --mt5 PYPL   # dry-run MT5 order
  python cli.py examples/paypal_2026.py --mt5 PYPL --live  # live order (careful)
"""

import sys
import importlib.util
import argparse
from pathlib import Path


def load_example(path: str):
    spec = importlib.util.spec_from_file_location("example", path)
    mod = importlib.util.module_from_spec(spec)
    # add project root to sys.path so 'from aladdin import ...' works
    sys.path.insert(0, str(Path(__file__).parent))
    spec.loader.exec_module(mod)
    return mod.params


def main():
    parser = argparse.ArgumentParser(description="aladdin-mini: disclosure → market signal")
    parser.add_argument("example", help="path to example file (e.g. examples/paypal_2026.py)")
    parser.add_argument("--mt5", metavar="SYMBOL", help="MT5 symbol to trade (e.g. PYPL)")
    parser.add_argument("--live", action="store_true", help="place real order (default: dry run)")
    args = parser.parse_args()

    from aladdin import compute
    params = load_example(args.example)
    result = compute(params)

    print("\naladdin-mini — disclosure impact signal")
    print("=" * 45)
    print(result.summary())
    print()

    if args.mt5:
        from aladdin.mt5_bridge import connect, place_signal, disconnect
        connected = connect()
        if connected or not args.live:
            out = place_signal(result, args.mt5, dry_run=not args.live)
            print(f"[mt5] result: {out}")
            if connected:
                disconnect()


if __name__ == "__main__":
    main()
