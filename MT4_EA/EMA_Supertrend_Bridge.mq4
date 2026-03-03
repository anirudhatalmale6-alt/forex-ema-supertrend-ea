//+------------------------------------------------------------------+
//| EMA_Supertrend_Bridge.mq4                                         |
//| TradingView Webhook → MT4 Trade Executor                         |
//| Reads signal files from webhook bridge and executes trades        |
//+------------------------------------------------------------------+
#property copyright "Forex Trend Follower"
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                  |
//+------------------------------------------------------------------+
// Signal Reading
input int    CheckIntervalMs  = 500;     // Signal check interval (milliseconds)
input string SignalPrefix     = "signal_"; // Signal file prefix

// Trade Settings
input double DefaultLotSize   = 0.01;    // Default lot size
input int    MaxSlippage       = 3;       // Max slippage in points
input int    MagicNumber       = 20260303; // Unique EA identifier
input string TradeComment      = "EMA+ST Bridge"; // Trade comment

// Risk Management
input int    MaxOpenTrades     = 1;       // Max simultaneous trades
input double MaxDrawdownPct    = 15.0;    // Max drawdown % (pause trading)

// Display
input bool   ShowDashboard     = true;    // Show info panel on chart

//+------------------------------------------------------------------+
//| GLOBAL VARIABLES                                                  |
//+------------------------------------------------------------------+
int    totalSignalsProcessed = 0;
int    totalTradesExecuted   = 0;
string lastSignalAction      = "None";
string lastError             = "";
datetime lastSignalTime      = 0;
bool   tradingPaused         = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
    // Set timer for signal checking
    EventSetMillisecondTimer(CheckIntervalMs);

    Print("===========================================");
    Print("EMA + Supertrend Bridge EA Initialized");
    Print("Magic Number: ", MagicNumber);
    Print("Default Lot: ", DefaultLotSize);
    Print("Max Open Trades: ", MaxOpenTrades);
    Print("Signal Check Interval: ", CheckIntervalMs, "ms");
    Print("===========================================");

    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Comment("");
    Print("Bridge EA stopped. Signals processed: ", totalSignalsProcessed,
          " | Trades executed: ", totalTradesExecuted);
}

//+------------------------------------------------------------------+
//| Timer function — checks for new signal files                     |
//+------------------------------------------------------------------+
void OnTimer()
{
    // Check drawdown
    CheckDrawdown();

    if(tradingPaused)
    {
        if(ShowDashboard) UpdateDashboard();
        return;
    }

    // Scan for signal files
    ProcessSignalFiles();

    // Update dashboard
    if(ShowDashboard) UpdateDashboard();
}

//+------------------------------------------------------------------+
//| Scan and process signal files                                     |
//+------------------------------------------------------------------+
void ProcessSignalFiles()
{
    string filename;
    long   searchHandle = FileFindFirst(SignalPrefix + "*.json", filename, 0);

    if(searchHandle == INVALID_HANDLE)
        return;  // No signal files found

    do
    {
        // Read signal file
        string signalJson = ReadSignalFile(filename);
        if(signalJson == "")
            continue;

        // Parse and execute
        if(ParseAndExecuteSignal(signalJson))
        {
            totalSignalsProcessed++;
        }

        // Delete processed signal file
        FileDelete(filename);

    } while(FileFindNext(searchHandle, filename));

    FileFindClose(searchHandle);
}

//+------------------------------------------------------------------+
//| Read signal file contents                                         |
//+------------------------------------------------------------------+
string ReadSignalFile(string filename)
{
    int handle = FileOpen(filename, FILE_READ | FILE_TXT | FILE_ANSI);
    if(handle == INVALID_HANDLE)
    {
        lastError = "Cannot open: " + filename;
        Print("Error: ", lastError);
        return "";
    }

    string content = "";
    while(!FileIsEnding(handle))
    {
        content += FileReadString(handle);
    }
    FileClose(handle);

    return content;
}

//+------------------------------------------------------------------+
//| Parse JSON signal and execute trade                               |
//+------------------------------------------------------------------+
bool ParseAndExecuteSignal(string json)
{
    // Simple JSON parser for our signal format
    string action  = GetJsonValue(json, "action");
    string symbol  = GetJsonValue(json, "symbol");
    string lotStr  = GetJsonValue(json, "lot");
    string slStr   = GetJsonValue(json, "sl");
    string comment = GetJsonValue(json, "comment");

    if(action == "")
    {
        lastError = "Missing action in signal";
        Print("Error: ", lastError);
        return false;
    }

    // Default values
    double lot = (lotStr != "") ? StringToDouble(lotStr) : DefaultLotSize;
    double sl  = (slStr != "")  ? StringToDouble(slStr)  : 0;
    if(symbol == "") symbol = Symbol();
    if(comment == "") comment = TradeComment;

    // Normalize symbol (add suffix if needed, e.g., GBPJPYm)
    symbol = NormalizeSymbolName(symbol);

    Print("Signal: action=", action, " symbol=", symbol, " lot=", lot, " sl=", sl);
    lastSignalAction = action;
    lastSignalTime   = TimeCurrent();

    // Execute based on action
    if(action == "buy")
        return ExecuteBuy(symbol, lot, sl, comment);
    else if(action == "sell")
        return ExecuteSell(symbol, lot, sl, comment);
    else if(action == "close_buy")
        return ClosePositions(symbol, OP_BUY);
    else if(action == "close_sell")
        return ClosePositions(symbol, OP_SELL);
    else if(action == "close_all")
        return CloseAllPositions(symbol);

    lastError = "Unknown action: " + action;
    Print("Error: ", lastError);
    return false;
}

//+------------------------------------------------------------------+
//| Execute BUY order                                                 |
//+------------------------------------------------------------------+
bool ExecuteBuy(string symbol, double lot, double sl, string comment)
{
    // Check max trades
    if(CountOpenTrades(symbol) >= MaxOpenTrades)
    {
        // Close existing sells first if we're reversing
        ClosePositions(symbol, OP_SELL);
    }

    if(CountOpenTrades(symbol) >= MaxOpenTrades)
    {
        Print("Max trades reached for ", symbol);
        return false;
    }

    double ask = MarketInfo(symbol, MODE_ASK);
    double point = MarketInfo(symbol, MODE_POINT);
    int digits = (int)MarketInfo(symbol, MODE_DIGITS);

    // Normalize SL
    if(sl > 0)
        sl = NormalizeDouble(sl, digits);

    int ticket = OrderSend(symbol, OP_BUY, lot, ask, MaxSlippage, sl, 0, comment, MagicNumber, 0, clrGreen);

    if(ticket > 0)
    {
        totalTradesExecuted++;
        Print("BUY executed: Ticket #", ticket, " | ", symbol, " @ ", ask, " | SL: ", sl);
        lastError = "";
        return true;
    }
    else
    {
        lastError = "BUY failed: " + IntegerToString(GetLastError());
        Print("Error: ", lastError);
        return false;
    }
}

//+------------------------------------------------------------------+
//| Execute SELL order                                                |
//+------------------------------------------------------------------+
bool ExecuteSell(string symbol, double lot, double sl, string comment)
{
    // Check max trades
    if(CountOpenTrades(symbol) >= MaxOpenTrades)
    {
        // Close existing buys first if we're reversing
        ClosePositions(symbol, OP_BUY);
    }

    if(CountOpenTrades(symbol) >= MaxOpenTrades)
    {
        Print("Max trades reached for ", symbol);
        return false;
    }

    double bid = MarketInfo(symbol, MODE_BID);
    double point = MarketInfo(symbol, MODE_POINT);
    int digits = (int)MarketInfo(symbol, MODE_DIGITS);

    // Normalize SL
    if(sl > 0)
        sl = NormalizeDouble(sl, digits);

    int ticket = OrderSend(symbol, OP_SELL, lot, bid, MaxSlippage, sl, 0, comment, MagicNumber, 0, clrRed);

    if(ticket > 0)
    {
        totalTradesExecuted++;
        Print("SELL executed: Ticket #", ticket, " | ", symbol, " @ ", bid, " | SL: ", sl);
        lastError = "";
        return true;
    }
    else
    {
        lastError = "SELL failed: " + IntegerToString(GetLastError());
        Print("Error: ", lastError);
        return false;
    }
}

//+------------------------------------------------------------------+
//| Close positions of a specific type                                |
//+------------------------------------------------------------------+
bool ClosePositions(string symbol, int type)
{
    bool allClosed = true;

    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
            continue;

        if(OrderMagicNumber() != MagicNumber)
            continue;

        if(OrderSymbol() != symbol)
            continue;

        if(OrderType() != type)
            continue;

        double closePrice = (type == OP_BUY) ?
            MarketInfo(symbol, MODE_BID) :
            MarketInfo(symbol, MODE_ASK);

        if(!OrderClose(OrderTicket(), OrderLots(), closePrice, MaxSlippage, clrYellow))
        {
            lastError = "Close failed: Ticket #" + IntegerToString(OrderTicket());
            Print("Error: ", lastError);
            allClosed = false;
        }
        else
        {
            Print("Closed: Ticket #", OrderTicket(), " | ", symbol);
        }
    }

    return allClosed;
}

//+------------------------------------------------------------------+
//| Close all positions for a symbol                                  |
//+------------------------------------------------------------------+
bool CloseAllPositions(string symbol)
{
    bool b = ClosePositions(symbol, OP_BUY);
    bool s = ClosePositions(symbol, OP_SELL);
    return b && s;
}

//+------------------------------------------------------------------+
//| Count open trades for a symbol                                    |
//+------------------------------------------------------------------+
int CountOpenTrades(string symbol)
{
    int count = 0;
    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
            continue;
        if(OrderMagicNumber() == MagicNumber && OrderSymbol() == symbol)
            count++;
    }
    return count;
}

//+------------------------------------------------------------------+
//| Check drawdown and pause if exceeded                              |
//+------------------------------------------------------------------+
void CheckDrawdown()
{
    double balance = AccountBalance();
    double equity  = AccountEquity();

    if(balance <= 0) return;

    double drawdownPct = ((balance - equity) / balance) * 100.0;

    if(drawdownPct >= MaxDrawdownPct)
    {
        if(!tradingPaused)
        {
            tradingPaused = true;
            Print("TRADING PAUSED: Drawdown ", DoubleToString(drawdownPct, 2),
                  "% exceeds limit ", DoubleToString(MaxDrawdownPct, 2), "%");
        }
    }
    else
    {
        if(tradingPaused)
        {
            tradingPaused = false;
            Print("Trading resumed: Drawdown recovered to ", DoubleToString(drawdownPct, 2), "%");
        }
    }
}

//+------------------------------------------------------------------+
//| Normalize symbol name (handle broker suffixes)                    |
//+------------------------------------------------------------------+
string NormalizeSymbolName(string symbol)
{
    // If the exact symbol exists, use it
    if(MarketInfo(symbol, MODE_BID) > 0)
        return symbol;

    // Try common suffixes (XM uses micro/standard suffixes)
    string suffixes[] = {"m", ".", ".m", "micro", "#", "-", "c"};
    for(int i = 0; i < ArraySize(suffixes); i++)
    {
        string test = symbol + suffixes[i];
        if(MarketInfo(test, MODE_BID) > 0)
        {
            Print("Symbol normalized: ", symbol, " → ", test);
            return test;
        }
    }

    // Return original if nothing found
    return symbol;
}

//+------------------------------------------------------------------+
//| Simple JSON value extractor                                       |
//+------------------------------------------------------------------+
string GetJsonValue(string json, string key)
{
    string searchKey = "\"" + key + "\"";
    int keyPos = StringFind(json, searchKey);
    if(keyPos < 0) return "";

    // Find colon after key
    int colonPos = StringFind(json, ":", keyPos + StringLen(searchKey));
    if(colonPos < 0) return "";

    int startPos = colonPos + 1;

    // Skip whitespace
    while(startPos < StringLen(json) &&
          (StringGetCharacter(json, startPos) == ' ' ||
           StringGetCharacter(json, startPos) == '\t' ||
           StringGetCharacter(json, startPos) == '\n' ||
           StringGetCharacter(json, startPos) == '\r'))
    {
        startPos++;
    }

    if(startPos >= StringLen(json)) return "";

    string value = "";

    // Check if value is a string (quoted)
    if(StringGetCharacter(json, startPos) == '"')
    {
        startPos++;  // Skip opening quote
        int endPos = StringFind(json, "\"", startPos);
        if(endPos < 0) return "";
        value = StringSubstr(json, startPos, endPos - startPos);
    }
    else
    {
        // Number or other value — read until comma, brace, or end
        int endPos = startPos;
        while(endPos < StringLen(json))
        {
            int ch = StringGetCharacter(json, endPos);
            if(ch == ',' || ch == '}' || ch == ']' || ch == '\n' || ch == '\r')
                break;
            endPos++;
        }
        value = StringSubstr(json, startPos, endPos - startPos);
        StringTrimLeft(value);
        StringTrimRight(value);
    }

    return value;
}

//+------------------------------------------------------------------+
//| Update on-chart dashboard                                         |
//+------------------------------------------------------------------+
void UpdateDashboard()
{
    double balance  = AccountBalance();
    double equity   = AccountEquity();
    double dd       = (balance > 0) ? ((balance - equity) / balance) * 100.0 : 0;
    int    trades   = CountOpenTrades(Symbol());

    string status = tradingPaused ? "PAUSED (Max DD)" : "ACTIVE";
    string statusColor = tradingPaused ? "RED" : "GREEN";

    string dash = "";
    dash += "━━━ EMA + Supertrend Bridge ━━━\n";
    dash += "Status: " + status + "\n";
    dash += "Balance: " + DoubleToString(balance, 2) + "\n";
    dash += "Equity: " + DoubleToString(equity, 2) + "\n";
    dash += "Drawdown: " + DoubleToString(dd, 2) + "%\n";
    dash += "Open Trades: " + IntegerToString(trades) + " / " + IntegerToString(MaxOpenTrades) + "\n";
    dash += "Signals Processed: " + IntegerToString(totalSignalsProcessed) + "\n";
    dash += "Trades Executed: " + IntegerToString(totalTradesExecuted) + "\n";
    dash += "Last Signal: " + lastSignalAction + "\n";

    if(lastSignalTime > 0)
        dash += "Last Signal Time: " + TimeToString(lastSignalTime, TIME_DATE|TIME_SECONDS) + "\n";

    if(lastError != "")
        dash += "Last Error: " + lastError + "\n";

    dash += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━";

    Comment(dash);
}

//+------------------------------------------------------------------+
//| OnTick — fallback signal check                                    |
//+------------------------------------------------------------------+
void OnTick()
{
    // OnTimer handles most checks, but process on tick too for responsiveness
    if(!tradingPaused)
        ProcessSignalFiles();
}
//+------------------------------------------------------------------+
