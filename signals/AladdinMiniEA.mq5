//+------------------------------------------------------------------+
//|                                              AladdinMiniEA.mq5   |
//|              RFI-IRFOS — github.com/rfi-irfos/aladdin-mini       |
//|                                          MIT License             |
//+------------------------------------------------------------------+
//
// SHS Expert Advisor for SQQQ/TQQQ on AvaTrade.
// Reads signals written by the Python aladdin-mini CLI into a file.
//
// Architecture:
//   1. Run aladdin-mini on your laptop:
//        python cli.py examples/paypal_2026.py --write-signal
//   2. Copy the generated aladdin_signal.txt to:
//        [MT5_Data]/MQL5/Files/aladdin_signal.txt
//      (on Windows: %APPDATA%\MetaQuotes\Terminal\<ID>\MQL5\Files\)
//   3. Enable this EA on any chart — it polls the file every 30s.
//
// Signal file format (pipe-delimited, one line):
//   STRONG_SHORT|0.64|91.4|elevated|PayPal (PYPL)|2026-06-23T09:12:00
//   ^ signal     ^conf ^score ^buffett ^company     ^timestamp
//
// SHS rules (Sniper-Hold-Strike):
//   - No hard stop-loss (mental only, stop-hunt-proof)
//   - TP always set at SHS_TP_PCT away from entry
//   - 33% of equity always reserved (never risked)
//   - Stage 1: micro layers (1→2→4→8 shares)
//   - Stage 3: killshot (15 shares) on confirmation
//   - NEUTRAL signal: close all and go flat
//
// NASDAQ-specific: SQQQ + TQQQ are inverse/leveraged ETF CFDs.
//   STRONG_SHORT → BUY SQQQ  (profits when NASDAQ falls)
//   STRONG_SHORT → SELL TQQQ (optional; see USE_TQQQ_HEDGE)
//   NEUTRAL      → close everything
//
#property copyright "RFI-IRFOS"
#property link      "https://github.com/rfi-irfos/aladdin-mini"
#property version   "1.00"
#property description "SHS position system driven by aladdin-mini disclosure signals (SQQQ/TQQQ)"
#property strict

//--- Input parameters
input string   SignalFile         = "aladdin_signal.txt";  // Signal file (MQL5/Files/)
input string   SymbolSQQQ        = "SQQQ";                 // 3x inverse NASDAQ ETF
input string   SymbolTQQQ        = "TQQQ";                 // 3x long NASDAQ ETF
input bool     UseTQQQHedge      = false;                  // Also sell TQQQ on SHORT signal
input double   CashReserveRatio  = 0.33;                   // Equity fraction always reserved
input double   SHS_TP_PCT        = 0.05;                   // Take-profit: 5% from entry
input int      TimerSeconds      = 30;                     // Signal poll interval (seconds)
input bool     EnableTrading     = false;                  // SAFETY: must set true for live orders
input int      MagicNumber       = 20260623;               // Unique order identifier

// SHS stage-1 lot sizes (shares)
input double   Layer1_Shares     = 1.0;
input double   Layer2_Shares     = 2.0;
input double   Layer3_Shares     = 4.0;
input double   Layer4_Shares     = 8.0;
input double   Killshot_Shares   = 15.0;

//--- State
string  g_signal       = "NEUTRAL";
string  g_last_signal  = "";
int     g_shs_stage    = 0;   // 0=flat 1=layering 2=awaiting_confirmation 3=killshot
int     g_layer_count  = 0;
double  g_entry_price  = 0.0;
string  g_company      = "";

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("[aladdin-mini] EA v1.00 loaded");
    Print("[aladdin-mini] Signal file: ", SignalFile);
    Print("[aladdin-mini] Symbols: ", SymbolSQQQ, " / ", SymbolTQQQ);
    if(!EnableTrading)
        Print("[aladdin-mini] *** DRY RUN MODE *** Set EnableTrading=true for live orders");

    EventSetTimer(TimerSeconds);
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("[aladdin-mini] EA removed");
}

//+------------------------------------------------------------------+
//| Timer: poll signal file and act                                  |
//+------------------------------------------------------------------+
void OnTimer()
{
    string sig = ReadSignal();
    if(sig == "") return;

    if(sig != g_last_signal)
    {
        Print("[aladdin-mini] Signal: ", g_last_signal == "" ? "(none)" : g_last_signal, " -> ", sig,
              " | company: ", g_company, " | stage: ", g_shs_stage);
        g_last_signal = sig;
        g_signal = sig;
        HandleSignal(sig);
    }
}

//+------------------------------------------------------------------+
//| Parse signal file                                                |
//+------------------------------------------------------------------+
string ReadSignal()
{
    int fh = FileOpen(SignalFile, FILE_READ | FILE_TXT | FILE_ANSI);
    if(fh == INVALID_HANDLE) return "";

    string line = FileReadString(fh);
    FileClose(fh);

    if(StringLen(line) == 0) return "";

    // Format: SIGNAL|CONFIDENCE|SCORE|BUFFETT_TIER|COMPANY|TIMESTAMP
    string parts[];
    int n = StringSplit(line, '|', parts);

    string sig = StringTrimRight(StringTrimLeft(n > 0 ? parts[0] : "NEUTRAL"));
    g_company   = n > 4 ? StringTrimRight(StringTrimLeft(parts[4])) : "unknown";

    return sig;
}

//+------------------------------------------------------------------+
//| Main signal handler                                              |
//+------------------------------------------------------------------+
void HandleSignal(string signal)
{
    if(!EnableTrading)
    {
        Print("[DRY] Signal=", signal, " SHS_Stage=", g_shs_stage, " Layers=", g_layer_count);
        PrintAccountState();
        SimulateSHS(signal);
        return;
    }

    if(signal == "STRONG_SHORT" || signal == "SHORT")
    {
        // Close any existing TQQQ longs (wrong direction)
        CloseByMagic(SymbolTQQQ, true);

        if(!CashOK())
        {
            Print("[SHS] Cash reserve below ", DoubleToString(CashReserveRatio * 100, 0),
                  "% — skipping entry");
            return;
        }

        double shares = NextLayerShares();
        if(shares <= 0) return;

        double ask = SymbolInfoDouble(SymbolSQQQ, SYMBOL_ASK);
        double tp  = ask * (1.0 + SHS_TP_PCT);

        bool ok = SendOrder(SymbolSQQQ, ORDER_TYPE_BUY, shares, ask, tp);
        if(ok)
        {
            g_layer_count++;
            if(g_shs_stage == 0) { g_shs_stage = 1; g_entry_price = ask; }
            if(g_layer_count >= 4) g_shs_stage = 2;

            Print("[SHS] Layer ", g_layer_count, " — ", shares, " shares ", SymbolSQQQ,
                  " @ ", ask, "  TP: ", tp, "  Stage: ", g_shs_stage);

            if(UseTQQQHedge)
            {
                double bid = SymbolInfoDouble(SymbolTQQQ, SYMBOL_BID);
                SendOrder(SymbolTQQQ, ORDER_TYPE_SELL, shares * 0.5, bid, 0.0);
            }
        }
    }
    else if(signal == "WATCH")
    {
        Print("[SHS] WATCH — holding positions, no new entries");
    }
    else   // NEUTRAL
    {
        int closed = CloseByMagic(SymbolSQQQ, false);
        closed    += CloseByMagic(SymbolTQQQ, false);
        if(closed > 0)
        {
            g_shs_stage   = 0;
            g_layer_count = 0;
            g_entry_price = 0.0;
            Print("[SHS] NEUTRAL — ", closed, " position(s) closed. Flat.");
        }
    }

    PrintAccountState();
}

//+------------------------------------------------------------------+
//| SHS: next stage-1 lot size                                       |
//+------------------------------------------------------------------+
double NextLayerShares()
{
    if(g_shs_stage >= 2)
    {
        Print("[SHS] Stage-1 complete — waiting for daily/weekly confirmation");
        return 0.0;
    }
    switch(g_layer_count)
    {
        case 0: return Layer1_Shares;
        case 1: return Layer2_Shares;
        case 2: return Layer3_Shares;
        case 3: return Layer4_Shares;
    }
    return 0.0;
}

//--- Call this from a separate button EA or manually via Script
//    after daily + weekly confirmation bars close with the trend.
void FireKillshot()
{
    if(g_shs_stage != 2)
    {
        Print("[SHS] Not in Stage 2 — killshot refused (stage=", g_shs_stage, ")");
        return;
    }
    if(!CashOK())
    {
        Print("[SHS] Cash reserve too low for killshot");
        return;
    }
    double ask = SymbolInfoDouble(SymbolSQQQ, SYMBOL_ASK);
    double tp  = ask * (1.0 + SHS_TP_PCT * 1.5);  // wider TP for killshot

    if(SendOrder(SymbolSQQQ, ORDER_TYPE_BUY, Killshot_Shares, ask, tp))
    {
        g_shs_stage = 3;
        Print("[SHS] *** KILLSHOT *** ", Killshot_Shares, " shares ", SymbolSQQQ,
              " @ ", ask, "  Sniper, not machine gun.");
    }
}

//+------------------------------------------------------------------+
//| 33% cash reserve check                                           |
//+------------------------------------------------------------------+
bool CashOK()
{
    double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
    double margin  = AccountInfoDouble(ACCOUNT_MARGIN);
    double reserve = equity * CashReserveRatio;
    return (equity - margin) >= reserve;
}

//+------------------------------------------------------------------+
//| Place an order                                                   |
//+------------------------------------------------------------------+
bool SendOrder(string symbol, ENUM_ORDER_TYPE type, double lots, double price, double tp)
{
    MqlTradeRequest req = {};
    MqlTradeResult  res = {};

    req.action    = TRADE_ACTION_DEAL;
    req.symbol    = symbol;
    req.volume    = lots;
    req.type      = type;
    req.price     = price;
    req.tp        = tp;
    req.sl        = 0.0;         // SHS: no hard SL, ever
    req.deviation = 15;
    req.magic     = MagicNumber;
    req.comment   = "aladdin-mini " + g_company;
    req.type_time    = ORDER_TIME_GTC;
    req.type_filling = ORDER_FILLING_IOC;

    bool ok = OrderSend(req, res);
    if(!ok || res.retcode != TRADE_RETCODE_DONE)
        Print("[aladdin-mini] Order failed: ", res.retcode, " — ", res.comment);
    return ok && res.retcode == TRADE_RETCODE_DONE;
}

//+------------------------------------------------------------------+
//| Close all aladdin-mini positions for a symbol                   |
//+------------------------------------------------------------------+
int CloseByMagic(string symbol, bool only_longs)
{
    int closed = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(PositionGetSymbol(i) != symbol) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

        ENUM_POSITION_TYPE pt = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
        if(only_longs && pt != POSITION_TYPE_BUY) continue;

        ulong ticket = PositionGetInteger(POSITION_TICKET);
        MqlTradeRequest req = {};
        MqlTradeResult  res = {};

        req.action   = TRADE_ACTION_DEAL;
        req.symbol   = symbol;
        req.volume   = PositionGetDouble(POSITION_VOLUME);
        req.type     = (pt == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
        req.price    = (req.type == ORDER_TYPE_SELL)
                       ? SymbolInfoDouble(symbol, SYMBOL_BID)
                       : SymbolInfoDouble(symbol, SYMBOL_ASK);
        req.position = ticket;
        req.deviation = 15;
        req.magic    = MagicNumber;
        req.comment  = "aladdin-mini close";

        if(OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE) closed++;
    }
    return closed;
}

//+------------------------------------------------------------------+
//| Dry run simulator                                                |
//+------------------------------------------------------------------+
void SimulateSHS(string signal)
{
    if(signal == "STRONG_SHORT" || signal == "SHORT")
    {
        double shares = NextLayerShares();
        if(shares > 0)
        {
            g_layer_count++;
            if(g_shs_stage == 0) g_shs_stage = 1;
            if(g_layer_count >= 4) g_shs_stage = 2;
            Print("[DRY] BUY ", shares, " shares ", SymbolSQQQ,
                  "  Layer=", g_layer_count, "  Stage=", g_shs_stage);
        }
    }
    else if(signal == "NEUTRAL")
    {
        if(g_layer_count > 0)
            Print("[DRY] CLOSE ", g_layer_count, " layers — flat");
        g_shs_stage = 0; g_layer_count = 0;
    }
}

void PrintAccountState()
{
    double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double margin  = AccountInfoDouble(ACCOUNT_MARGIN);
    Print("[Account] Balance=", DoubleToString(balance, 2),
          " Equity=", DoubleToString(equity, 2),
          " Margin=", DoubleToString(margin, 2),
          " SHS=", g_shs_stage, "/", g_layer_count,
          " Enabled=", EnableTrading);
}
