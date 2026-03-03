# EMA 9/26 + Supertrend Strategy — Setup Guide
## TradingView → MT4 (XM) Automated Trading

---

## Overview

This system has 3 components:
1. **Pine Script** — Runs on TradingView, generates buy/sell alerts
2. **Webhook Bridge** — Python server that receives alerts from TradingView
3. **MT4 EA** — Expert Advisor on your XM MT4 that executes the trades

```
TradingView Alert → Webhook (your PC/VPS) → Signal File → MT4 EA → Trade on XM
```

---

## STEP 1: Install the Pine Script on TradingView

1. Open TradingView → Pine Editor (bottom panel)
2. Click **Open** → **New blank indicator**
3. Delete all existing code
4. Copy-paste the entire contents of `EMA_Supertrend_Strategy.pine`
5. Click **Save** → Name it "EMA + Supertrend Trend Follower"
6. Click **Add to Chart**
7. Select **GBP/JPY** pair, **5 minute** timeframe

You should now see:
- Blue line = EMA 9
- Orange line = EMA 26
- Green/Red line = Supertrend
- Triangle arrows = Entry signals
- Info panel (top right) showing current state

### Run the Backtest in TradingView
1. Click the **Strategy Tester** tab (bottom panel)
2. You'll see the equity curve and trade list
3. Click **Settings** (gear icon) to adjust parameters

---

## STEP 2: Set Up the Webhook Bridge

### Requirements
- Python 3.7+ installed on your PC or a VPS
- Port forwarding (if running on your PC) or a VPS with a public IP

### Option A: Run on Your PC
```bash
# Install Python if not installed
# Download from https://www.python.org/downloads/

# Run the bridge server
python server.py --port 5000

# With authentication token (recommended)
python server.py --port 5000 --token YOUR_SECRET_KEY
```

You'll also need to set up port forwarding on your router to forward port 5000 to your PC.

### Option B: Run on a VPS (Recommended)
```bash
# On your VPS (e.g., DigitalOcean, AWS, etc.)
python3 server.py --port 5000 --token YOUR_SECRET_KEY

# To run in background:
nohup python3 server.py --port 5000 --token YOUR_SECRET_KEY &
```

### Point signals to MT4
By default, the bridge writes signal files to a `signals/` folder. To connect it to MT4:

```bash
# Find your MT4 data folder:
# In MT4 → File → Open Data Folder → MQL4 → Files

# Run the bridge with that path:
python server.py --port 5000 --signals-dir "C:\Users\YOU\AppData\Roaming\MetaQuotes\Terminal\XXXX\MQL4\Files"
```

---

## STEP 3: Set Up TradingView Alerts

1. On your GBP/JPY 5min chart with the strategy loaded
2. Click **Alert** (alarm clock icon) or press Alt+A
3. Set:
   - **Condition**: "EMA + Supertrend Trend Follower"
   - **Trigger**: "Any alert() function call"
4. Under **Notifications** → Enable **Webhook URL**
5. Enter your webhook URL:
   ```
   http://YOUR_IP_OR_VPS:5000/
   ```
6. If using a token, add it to the alert message template:
   - The Pine Script already sends JSON format alerts
   - Just ensure the webhook URL is correct
7. Click **Create**

**Note**: TradingView webhook alerts require a **paid plan** (Pro or higher).

---

## STEP 4: Install the MT4 EA

1. Open MT4 on your XM account
2. Go to **File** → **Open Data Folder**
3. Navigate to `MQL4` → `Experts`
4. Copy `EMA_Supertrend_Bridge.mq4` into this folder
5. Restart MT4 (or right-click "Expert Advisors" in Navigator → Refresh)
6. Drag **EMA_Supertrend_Bridge** onto your **GBP/JPY** chart

### EA Settings
| Setting | Default | Description |
|---------|---------|-------------|
| CheckIntervalMs | 500 | How often to check for signals (ms) |
| DefaultLotSize | 0.01 | Trade lot size |
| MaxSlippage | 3 | Maximum slippage in points |
| MagicNumber | 20260303 | Unique EA identifier |
| MaxOpenTrades | 1 | Max simultaneous trades |
| MaxDrawdownPct | 15.0 | Pause trading if drawdown exceeds this % |

### Enable Auto Trading
1. Click **Tools** → **Options** → **Expert Advisors**
2. Check ✅ **Allow automated trading**
3. Check ✅ **Allow DLL imports** (not required but good practice)
4. Click the **AutoTrading** button on the toolbar (should be green)
5. Make sure the smiley face 😊 appears on the chart (not a sad face)

---

## STEP 5: Test the Full Pipeline

1. Start the webhook bridge: `python server.py --port 5000`
2. Ensure the MT4 EA is running (green smiley on chart)
3. On TradingView, you can manually trigger a test alert
4. Check the MT4 Experts tab (bottom panel) for log messages
5. Check the webhook bridge console for incoming alerts

### Test with a manual webhook (from another terminal):
```bash
curl -X POST http://localhost:5000/ -H "Content-Type: application/json" -d '{"action":"buy","symbol":"GBPJPY","lot":0.01,"sl":190.500,"comment":"Test"}'
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| EA shows sad face | Enable AutoTrading in MT4 |
| No signals received | Check webhook URL, firewall, port forwarding |
| Symbol not found | XM may use "GBPJPYm" for micro accounts — EA auto-detects this |
| Trades not executing | Check Experts tab for errors, ensure trading is allowed |
| Bridge can't write files | Check the signals directory path is correct |

---

## File Structure

```
├── EMA_Supertrend_Strategy.pine    # Pine Script (TradingView)
├── webhook_bridge/
│   └── server.py                   # Webhook bridge server
├── MT4_EA/
│   └── EMA_Supertrend_Bridge.mq4   # MT4 Expert Advisor
├── backtest/
│   ├── backtester.py               # Python backtester
│   ├── multi_tf_backtest.py        # Multi-timeframe backtest
│   └── results/                    # Backtest reports & charts
└── SETUP_GUIDE.md                  # This file
```
