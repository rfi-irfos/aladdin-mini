[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MT5](https://img.shields.io/badge/broker-AvaTrade%20MT5-orange.svg)](https://www.avatrade.com/)
[![50 Parameters](https://img.shields.io/badge/model-50%20parameters-purple.svg)](#the-50-parameters)
[![SHS](https://img.shields.io/badge/system-Simeon%20Hedge%20System-red.svg)](#shs-position-system)
[![Credo](https://img.shields.io/badge/credo-sniper%2C%20not%20machine%20gun-black.svg)](#)

# aladdin-mini

open-source disclosure impact trading signal engine + position management system.

named after blackrock's aladdin ($21T AUM). this one is smaller. and free.

---

## what it does

two independent modules that work together:

**1. disclosure impact model** — 50-parameter causality chain: security/privacy disclosure → market signal.
models regulatory exposure, corporate response dynamics, media velocity, and market propagation to produce a structured trading signal (STRONG_SHORT / SHORT / WATCH / NEUTRAL).

**2. SHS (Simeon Hedge System)** — position building system for trend trading.
- stage 1: linear micro layering against the move (0.01 → 0.10 → 0.25 → 0.50 lots)
- stage 2: wait for daily/weekly chart confirmation
- stage 3: 1-lot killshot — simultaneously the stop-loss and the profit maximizer
- TP always set. SL never set (mental only — stop-hunt-proof).
- 33% cash reserve enforced at all times.

> "sniper, not machine gun."

---

## install

```bash
git clone https://github.com/rfi-irfos/aladdin-mini
cd aladdin-mini
pip install -r requirements.txt   # MetaTrader5 (optional, for live trading)
```

---

## usage

```bash
# compute disclosure impact signal
python cli.py examples/paypal_2026.py

# dry-run MT5 order via SHS
python cli.py examples/snapchat_2026.py --mt5 NAS100

# live order (MT5 terminal must be running)
python cli.py examples/paypal_2026.py --mt5 NAS100 --live
```

---

## example output

```
aladdin-mini — disclosure impact signal
=============================================
  company              PayPal (PYPL)
  signal               STRONG_SHORT  (confidence 64%)
  impact score         91.4/100
  price day-1 est.     -25.00%
  price 30-day est.    -40.00%
  sector spillover     -8.25%
  fine P50             €982,553,072
  enforcement prob.    51%
  class action exp.    $2,015,000,000
  reputational cost    0.98/1.0
```

---

## the 50 parameters

five layers:

| layer | parameters |
|-------|-----------|
| 1. finding characteristics | severity, evidence strength, GDPR article tier, data sensitivity, children flag, chinese entity flag |
| 2. regulatory exposure | lead DPA tier, prior fines, fine ceiling (4% turnover), BCC regulators, EDPB, noyb |
| 3. corporate response | DPO response time, bug bounty, legal team size, prior settlements, EU revenue fraction |
| 4. market signal | market cap, beta, short interest, IV, index membership, analyst coverage, sector contagion |
| 5. media & social velocity | media pickup speed, outlet tier, social velocity, WSB mention, class action speed |

empirical anchors: Amazon CNPD €746M, Meta DSB €1.2B, Equifax $700M, British Airways £20M.

---

## SHS position system

```python
from aladdin import SHSState
from aladdin.mt5_bridge import shs_add_layer, shs_killshot

state = SHSState(symbol="USDJPY", direction="BUY", account_balance=7000)

# stage 1: layer in as market moves against you
shs_add_layer(state, dry_run=True)   # 0.01 lot
shs_add_layer(state, dry_run=True)   # 0.10 lot
shs_add_layer(state, dry_run=True)   # 0.25 lot
shs_add_layer(state, dry_run=True)   # 0.50 lot → auto-advances to stage 2

# stage 2: wait. daily + weekly chart must confirm.

# stage 3: fire
shs_killshot(state, dry_run=True)    # 1.00 lot killshot
```

preferred assets: USDJPY, USDHUF, NAS100.

---

## architecture

```
aladdin/
  params.py      — DisclosureParams (50 fields)
  model.py       — cascade computation (layers 1-5)
  shs.py         — Simeon Hedge System position logic
  mt5_bridge.py  — AvaTrade MT5 connector (Wine on Linux supported)
examples/
  paypal_2026.py
  snapchat_2026.py
cli.py
```

---

## disclaimer

this is a research tool, not financial advice. past performance of the SHS system is not indicative of future results. use at your own risk. the disclosure impact model is a quantitative approximation based on publicly observable inputs — it does not constitute insider information.

---

## license

MIT

---

built by [RFI-IRFOS](https://ternlang.com) — Research Focus Institute, Interdisciplinary Research Facility for Open Sciences.  
ZVR 1015608684 · GISA 39261441 · Graz, Austria.
