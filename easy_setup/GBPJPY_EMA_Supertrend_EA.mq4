//+------------------------------------------------------------------+
//| GBPJPY_EMA_Supertrend_EA.mq4                                     |
//| Standalone EMA 9/26 + Supertrend Strategy                        |
//| Runs entirely inside MT4 — no external bridge needed             |
//+------------------------------------------------------------------+
#property copyright "GBPJPY Trend Follower"
#property version   "1.00"
#property strict
#property description "EMA 9/26 Crossover + Supertrend Confirmation"
#property description "Pair: GBPJPY | Timeframe: M5"
#property description "Fully automated entry, exit, and trailing SL"

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                  |
//+------------------------------------------------------------------+
// EMA Settings
input int    EMA_Fast_Period   = 9;       // Fast EMA Period
input int    EMA_Slow_Period   = 26;      // Slow EMA Period

// Supertrend Settings
input int    ST_ATR_Period     = 10;      // Supertrend ATR Period
input double ST_Multiplier     = 3.0;     // Supertrend Multiplier

// Trade Settings
input double LotSize           = 0.01;    // Lot Size
input int    SL_Buffer_Points  = 50;      // Stop Loss Buffer (points)
input int    Max_SL_Points     = 300;     // Maximum Stop Loss (points)
input int    MaxSlippage        = 3;       // Max Slippage (points)
input int    MagicNumber        = 20260309;// Unique EA ID

// Risk Management
input double MaxDrawdownPct    = 15.0;    // Max Drawdown % (pauses trading)
input int    MaxOpenTrades      = 1;       // Max Open Trades

// Display
input bool   ShowDashboard     = true;    // Show Dashboard on Chart

//+------------------------------------------------------------------+
//| GLOBAL VARIABLES                                                  |
//+------------------------------------------------------------------+
// Confirmation flags (persistent across ticks)
bool emaBullConfirmed = false;
bool emaBearConfirmed = false;

// Statistics
int    totalTrades     = 0;
int    totalWins       = 0;
int    totalLosses     = 0;
string lastAction      = "None";
bool   tradingPaused   = false;

// Previous bar tracking (to detect new bars)
datetime lastBarTime   = 0;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("=============================================");
    Print("GBPJPY EMA + Supertrend EA Initialized");
    Print("EMA: ", EMA_Fast_Period, "/", EMA_Slow_Period);
    Print("Supertrend: ATR ", ST_ATR_Period, " x ", ST_Multiplier);
    Print("Lot Size: ", LotSize);
    Print("SL Buffer: ", SL_Buffer_Points, " pts | Max SL: ", Max_SL_Points, " pts");
    Print("=============================================");

    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Comment("");
    Print("EA stopped. Trades: ", totalTrades, " | Wins: ", totalWins, " | Losses: ", totalLosses);
}

//+------------------------------------------------------------------+
//| Main tick function                                                |
//+------------------------------------------------------------------+
void OnTick()
{
    // Check drawdown
    CheckDrawdown();

    if(tradingPaused)
    {
        if(ShowDashboard) UpdateDashboard();
        return;
    }

    // Only process on new bar close (avoids multiple signals per candle)
    if(!IsNewBar())
    {
        // Still update trailing SL on every tick
        UpdateTrailingStop();
        if(ShowDashboard) UpdateDashboard();
        return;
    }

    // Calculate indicators on the PREVIOUS closed bar (shift=1)
    double emaFast_1   = iMA(NULL, 0, EMA_Fast_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
    double emaSlow_1   = iMA(NULL, 0, EMA_Slow_Period, 0, MODE_EMA, PRICE_CLOSE, 1);
    double emaFast_2   = iMA(NULL, 0, EMA_Fast_Period, 0, MODE_EMA, PRICE_CLOSE, 2);
    double emaSlow_2   = iMA(NULL, 0, EMA_Slow_Period, 0, MODE_EMA, PRICE_CLOSE, 2);

    // Candle data (previous closed bar)
    double closeBar1   = iClose(NULL, 0, 1);
    double openBar1    = iOpen(NULL, 0, 1);

    // EMA Crossover detection
    bool bullCross = (emaFast_2 <= emaSlow_2) && (emaFast_1 > emaSlow_1);
    bool bearCross = (emaFast_2 >= emaSlow_2) && (emaFast_1 < emaSlow_1);

    // Candle confirmation
    bool bullCandle = closeBar1 > openBar1;
    bool bearCandle = closeBar1 < openBar1;

    // Supertrend
    double stValue_1;
    int    stDir_1;
    CalcSupertrend(1, stValue_1, stDir_1);

    bool superBull = (stDir_1 < 0);  // Supertrend below price = bullish
    bool superBear = (stDir_1 > 0);  // Supertrend above price = bearish

    // Update confirmation flags
    if(bullCross && bullCandle)
    {
        emaBullConfirmed = true;
        emaBearConfirmed = false;
        Print("EMA Bull Cross CONFIRMED (candle validation passed)");
    }

    if(bearCross && bearCandle)
    {
        emaBearConfirmed = true;
        emaBullConfirmed = false;
        Print("EMA Bear Cross CONFIRMED (candle validation passed)");
    }

    // Entry signals
    bool buySignal  = emaBullConfirmed && superBull;
    bool sellSignal = emaBearConfirmed && superBear;

    int currentPos = GetCurrentPosition();

    // ===== EXIT LOGIC (check before entries) =====
    // Exit long: bear cross OR supertrend turns bearish
    if(currentPos > 0 && (bearCross || superBear))
    {
        ClosePositions(OP_BUY);
        Print("EXIT LONG: ", bearCross ? "Bear EMA Cross" : "Supertrend Bearish");
        lastAction = "Exit Long";
    }

    // Exit short: bull cross OR supertrend turns bullish
    if(currentPos < 0 && (bullCross || superBull))
    {
        ClosePositions(OP_SELL);
        Print("EXIT SHORT: ", bullCross ? "Bull EMA Cross" : "Supertrend Bullish");
        lastAction = "Exit Short";
    }

    // Refresh position after exits
    currentPos = GetCurrentPosition();

    // ===== ENTRY LOGIC =====
    // Buy entry
    if(buySignal && currentPos <= 0)
    {
        if(currentPos < 0) ClosePositions(OP_SELL);  // Close opposite first

        double sl = CalcBuySL(stValue_1);
        if(ExecuteBuy(sl))
        {
            emaBullConfirmed = false;
            lastAction = "BUY Entry";
            Print("BUY ENTRY: EMA Bull confirmed + Supertrend Bullish | SL: ", sl);
        }
    }

    // Sell entry
    if(sellSignal && currentPos >= 0)
    {
        if(currentPos > 0) ClosePositions(OP_BUY);  // Close opposite first

        double sl = CalcSellSL(stValue_1);
        if(ExecuteSell(sl))
        {
            emaBearConfirmed = false;
            lastAction = "SELL Entry";
            Print("SELL ENTRY: EMA Bear confirmed + Supertrend Bearish | SL: ", sl);
        }
    }

    if(ShowDashboard) UpdateDashboard();
}

//+------------------------------------------------------------------+
//| Supertrend Calculation                                            |
//+------------------------------------------------------------------+
void CalcSupertrend(int shift, double &stValue, int &stDirection)
{
    // Calculate ATR
    double atr = iATR(NULL, 0, ST_ATR_Period, shift);

    double highVal = iHigh(NULL, 0, shift);
    double lowVal  = iLow(NULL, 0, shift);
    double closeVal = iClose(NULL, 0, shift);
    double hl2 = (highVal + lowVal) / 2.0;

    double upperBand = hl2 + (ST_Multiplier * atr);
    double lowerBand = hl2 - (ST_Multiplier * atr);

    // We need to iterate from far back to build Supertrend properly
    // Use a simplified approach with enough lookback
    int lookback = 100;

    double prevUpper[], prevLower[], prevClose[], prevST[];
    int prevDir[];
    ArrayResize(prevUpper, lookback);
    ArrayResize(prevLower, lookback);
    ArrayResize(prevClose, lookback);
    ArrayResize(prevST, lookback);
    ArrayResize(prevDir, lookback);

    // Calculate from far back
    for(int i = lookback - 1; i >= 0; i--)
    {
        int s = shift + i;
        double a = iATR(NULL, 0, ST_ATR_Period, s);
        double h = iHigh(NULL, 0, s);
        double l = iLow(NULL, 0, s);
        double c = iClose(NULL, 0, s);
        double mid = (h + l) / 2.0;

        double ub = mid + (ST_Multiplier * a);
        double lb = mid - (ST_Multiplier * a);

        int idx = lookback - 1 - i;
        prevClose[idx] = c;

        if(idx == 0)
        {
            prevUpper[idx] = ub;
            prevLower[idx] = lb;
            prevDir[idx] = -1;  // Start bullish
            prevST[idx] = lb;
        }
        else
        {
            // Adjust bands based on previous values
            if(lb > prevLower[idx-1])
                prevLower[idx] = lb;
            else if(prevClose[idx-1] > prevLower[idx-1])
                prevLower[idx] = lb;
            else
                prevLower[idx] = prevLower[idx-1];

            if(ub < prevUpper[idx-1])
                prevUpper[idx] = ub;
            else if(prevClose[idx-1] < prevUpper[idx-1])
                prevUpper[idx] = ub;
            else
                prevUpper[idx] = prevUpper[idx-1];

            // Determine direction
            if(prevDir[idx-1] == -1)  // Was bullish
            {
                if(c < prevLower[idx])
                {
                    prevDir[idx] = 1;   // Turn bearish
                    prevST[idx] = prevUpper[idx];
                }
                else
                {
                    prevDir[idx] = -1;  // Stay bullish
                    prevST[idx] = prevLower[idx];
                }
            }
            else  // Was bearish
            {
                if(c > prevUpper[idx])
                {
                    prevDir[idx] = -1;  // Turn bullish
                    prevST[idx] = prevLower[idx];
                }
                else
                {
                    prevDir[idx] = 1;   // Stay bearish
                    prevST[idx] = prevUpper[idx];
                }
            }
        }
    }

    // Return the most recent values
    stValue = prevST[lookback - 1];
    stDirection = prevDir[lookback - 1];
}

//+------------------------------------------------------------------+
//| Calculate Buy Stop Loss                                           |
//+------------------------------------------------------------------+
double CalcBuySL(double supertrendValue)
{
    double point = MarketInfo(Symbol(), MODE_POINT);
    int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);

    // SL = Supertrend line - buffer
    double slRaw = supertrendValue - (SL_Buffer_Points * point);

    // Cap at max SL
    double maxSL = Bid - (Max_SL_Points * point);
    double sl = MathMax(slRaw, maxSL);

    return NormalizeDouble(sl, digits);
}

//+------------------------------------------------------------------+
//| Calculate Sell Stop Loss                                          |
//+------------------------------------------------------------------+
double CalcSellSL(double supertrendValue)
{
    double point = MarketInfo(Symbol(), MODE_POINT);
    int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);

    // SL = Supertrend line + buffer
    double slRaw = supertrendValue + (SL_Buffer_Points * point);

    // Cap at max SL
    double maxSL = Ask + (Max_SL_Points * point);
    double sl = MathMin(slRaw, maxSL);

    return NormalizeDouble(sl, digits);
}

//+------------------------------------------------------------------+
//| Update Trailing Stop based on Supertrend                          |
//+------------------------------------------------------------------+
void UpdateTrailingStop()
{
    double stValue;
    int stDir;
    CalcSupertrend(0, stValue, stDir);  // Current bar supertrend

    double point = MarketInfo(Symbol(), MODE_POINT);
    int digits = (int)MarketInfo(Symbol(), MODE_DIGITS);

    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
        if(OrderMagicNumber() != MagicNumber) continue;
        if(OrderSymbol() != Symbol()) continue;

        if(OrderType() == OP_BUY)
        {
            double newSL = NormalizeDouble(stValue - (SL_Buffer_Points * point), digits);
            double maxSL = NormalizeDouble(Bid - (Max_SL_Points * point), digits);
            newSL = MathMax(newSL, maxSL);

            // Only move SL up (trail), never down
            if(newSL > OrderStopLoss() && newSL < Bid)
            {
                bool res = OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrGreen);
                if(res) Print("Trailing SL updated (BUY): ", newSL);
            }
        }
        else if(OrderType() == OP_SELL)
        {
            double newSL = NormalizeDouble(stValue + (SL_Buffer_Points * point), digits);
            double maxSL = NormalizeDouble(Ask + (Max_SL_Points * point), digits);
            newSL = MathMin(newSL, maxSL);

            // Only move SL down (trail), never up
            if((newSL < OrderStopLoss() || OrderStopLoss() == 0) && newSL > Ask)
            {
                bool res = OrderModify(OrderTicket(), OrderOpenPrice(), newSL, OrderTakeProfit(), 0, clrRed);
                if(res) Print("Trailing SL updated (SELL): ", newSL);
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Execute Buy Order                                                 |
//+------------------------------------------------------------------+
bool ExecuteBuy(double sl)
{
    if(CountOpenTrades() >= MaxOpenTrades)
    {
        Print("Max trades reached, skipping BUY");
        return false;
    }

    int ticket = OrderSend(Symbol(), OP_BUY, LotSize, Ask, MaxSlippage, sl, 0,
                           "EMA+ST Buy", MagicNumber, 0, clrGreen);

    if(ticket > 0)
    {
        totalTrades++;
        Print("BUY executed: Ticket #", ticket, " @ ", Ask, " | SL: ", sl);
        return true;
    }
    else
    {
        Print("BUY failed: Error ", GetLastError());
        return false;
    }
}

//+------------------------------------------------------------------+
//| Execute Sell Order                                                |
//+------------------------------------------------------------------+
bool ExecuteSell(double sl)
{
    if(CountOpenTrades() >= MaxOpenTrades)
    {
        Print("Max trades reached, skipping SELL");
        return false;
    }

    int ticket = OrderSend(Symbol(), OP_SELL, LotSize, Bid, MaxSlippage, sl, 0,
                           "EMA+ST Sell", MagicNumber, 0, clrRed);

    if(ticket > 0)
    {
        totalTrades++;
        Print("SELL executed: Ticket #", ticket, " @ ", Bid, " | SL: ", sl);
        return true;
    }
    else
    {
        Print("SELL failed: Error ", GetLastError());
        return false;
    }
}

//+------------------------------------------------------------------+
//| Close positions of a type                                         |
//+------------------------------------------------------------------+
void ClosePositions(int type)
{
    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
        if(OrderMagicNumber() != MagicNumber) continue;
        if(OrderSymbol() != Symbol()) continue;
        if(OrderType() != type) continue;

        double closePrice = (type == OP_BUY) ? Bid : Ask;

        if(OrderClose(OrderTicket(), OrderLots(), closePrice, MaxSlippage, clrYellow))
        {
            // Track win/loss
            if(OrderProfit() >= 0)
                totalWins++;
            else
                totalLosses++;

            Print("Closed: Ticket #", OrderTicket(), " P/L: ", OrderProfit());
        }
        else
        {
            Print("Close failed: Ticket #", OrderTicket(), " Error: ", GetLastError());
        }
    }
}

//+------------------------------------------------------------------+
//| Get current position direction                                    |
//+------------------------------------------------------------------+
int GetCurrentPosition()
{
    // Returns: 1 = long, -1 = short, 0 = flat
    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
        if(OrderMagicNumber() != MagicNumber) continue;
        if(OrderSymbol() != Symbol()) continue;

        if(OrderType() == OP_BUY) return 1;
        if(OrderType() == OP_SELL) return -1;
    }
    return 0;
}

//+------------------------------------------------------------------+
//| Count open trades                                                 |
//+------------------------------------------------------------------+
int CountOpenTrades()
{
    int count = 0;
    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
        if(OrderMagicNumber() == MagicNumber && OrderSymbol() == Symbol())
            count++;
    }
    return count;
}

//+------------------------------------------------------------------+
//| Check if new bar formed                                           |
//+------------------------------------------------------------------+
bool IsNewBar()
{
    datetime currentBarTime = iTime(NULL, 0, 0);
    if(currentBarTime != lastBarTime)
    {
        lastBarTime = currentBarTime;
        return true;
    }
    return false;
}

//+------------------------------------------------------------------+
//| Check drawdown                                                    |
//+------------------------------------------------------------------+
void CheckDrawdown()
{
    double balance = AccountBalance();
    double equity  = AccountEquity();
    if(balance <= 0) return;

    double dd = ((balance - equity) / balance) * 100.0;

    if(dd >= MaxDrawdownPct)
    {
        if(!tradingPaused)
        {
            tradingPaused = true;
            Print("TRADING PAUSED: Drawdown ", DoubleToString(dd, 2), "% >= ", DoubleToString(MaxDrawdownPct, 2), "%");
        }
    }
    else
    {
        if(tradingPaused)
        {
            tradingPaused = false;
            Print("Trading resumed: Drawdown recovered to ", DoubleToString(dd, 2), "%");
        }
    }
}

//+------------------------------------------------------------------+
//| Dashboard display                                                 |
//+------------------------------------------------------------------+
void UpdateDashboard()
{
    double balance = AccountBalance();
    double equity  = AccountEquity();
    double dd = (balance > 0) ? ((balance - equity) / balance) * 100.0 : 0;

    // Current indicator values
    double emaFast = iMA(NULL, 0, EMA_Fast_Period, 0, MODE_EMA, PRICE_CLOSE, 0);
    double emaSlow = iMA(NULL, 0, EMA_Slow_Period, 0, MODE_EMA, PRICE_CLOSE, 0);

    double stVal;
    int stDir;
    CalcSupertrend(0, stVal, stDir);

    string emaTrend = (emaFast > emaSlow) ? "BULLISH" : "BEARISH";
    string stTrend  = (stDir < 0) ? "BULLISH" : "BEARISH";
    string status   = tradingPaused ? "PAUSED (Max DD)" : "ACTIVE";
    string pos      = (GetCurrentPosition() > 0) ? "LONG" : (GetCurrentPosition() < 0) ? "SHORT" : "FLAT";

    string dash = "";
    dash += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    dash += "  GBPJPY EMA + Supertrend EA\n";
    dash += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n";
    dash += "Status: " + status + "\n";
    dash += "Position: " + pos + "\n";
    dash += "\n";
    dash += "━━ Indicators ━━\n";
    dash += "EMA " + IntegerToString(EMA_Fast_Period) + ": " + DoubleToString(emaFast, (int)MarketInfo(Symbol(), MODE_DIGITS)) + "\n";
    dash += "EMA " + IntegerToString(EMA_Slow_Period) + ": " + DoubleToString(emaSlow, (int)MarketInfo(Symbol(), MODE_DIGITS)) + "\n";
    dash += "EMA Trend: " + emaTrend + "\n";
    dash += "Supertrend: " + DoubleToString(stVal, (int)MarketInfo(Symbol(), MODE_DIGITS)) + "\n";
    dash += "ST Trend: " + stTrend + "\n";
    dash += "Bull Confirmed: " + (emaBullConfirmed ? "YES" : "NO") + "\n";
    dash += "Bear Confirmed: " + (emaBearConfirmed ? "YES" : "NO") + "\n";
    dash += "\n";
    dash += "━━ Account ━━\n";
    dash += "Balance: " + DoubleToString(balance, 2) + "\n";
    dash += "Equity: " + DoubleToString(equity, 2) + "\n";
    dash += "Drawdown: " + DoubleToString(dd, 2) + "%\n";
    dash += "\n";
    dash += "━━ Statistics ━━\n";
    dash += "Trades: " + IntegerToString(totalTrades) + "\n";
    dash += "Wins: " + IntegerToString(totalWins) + " | Losses: " + IntegerToString(totalLosses) + "\n";
    dash += "Last Action: " + lastAction + "\n";
    dash += "\n";
    dash += "━━ Settings ━━\n";
    dash += "Lot: " + DoubleToString(LotSize, 2) + "\n";
    dash += "SL Buffer: " + IntegerToString(SL_Buffer_Points) + " pts\n";
    dash += "Max SL: " + IntegerToString(Max_SL_Points) + " pts\n";
    dash += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━";

    Comment(dash);
}
//+------------------------------------------------------------------+
