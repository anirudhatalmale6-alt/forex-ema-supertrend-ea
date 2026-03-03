"""
=============================================================================
EMA 9/26 + Supertrend Strategy — 2-Year Backtest Engine
Pair: GBP/JPY | Timeframe: 5 min
=============================================================================
Downloads historical data and runs a full backtest with:
- Net P/L, Drawdown, Win Rate, Profit Factor, Sharpe Ratio
- Equity curve chart
- Monthly breakdown
- Trade log
=============================================================================
"""

import os
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# =============================================================================
# STRATEGY PARAMETERS
# =============================================================================
EMA_FAST = 9
EMA_SLOW = 26
ST_PERIOD = 10
ST_MULTIPLIER = 3.0
SL_BUFFER = 0.050       # 50 points for GBP/JPY
LOT_SIZE = 0.01
POINT_VALUE = 0.001     # 1 point for 3-decimal JPY pairs
PIP_VALUE_PER_LOT = 100 / 100  # Approximate for GBP/JPY mini lot (0.01)
INITIAL_BALANCE = 10000.0
SPREAD_POINTS = 20      # ~2 pips spread for GBP/JPY on XM (5min)


# =============================================================================
# DATA DOWNLOAD — using yfinance
# =============================================================================
def download_data(symbol="GBPJPY=X", period_years=2, interval="5m"):
    """
    Download historical data. yfinance limits 5m data to 60 days,
    so we download in chunks and concatenate.
    """
    try:
        import yfinance as yf
    except ImportError:
        print("Installing yfinance...")
        os.system("pip install yfinance -q")
        import yfinance as yf

    print(f"Downloading {symbol} {interval} data for {period_years} years...")

    all_data = []
    end_date = datetime.now()
    chunk_days = 59  # yfinance limit for intraday

    total_days = period_years * 365
    start_date = end_date - timedelta(days=total_days)
    current_start = start_date

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)
        try:
            df = yf.download(
                symbol,
                start=current_start.strftime("%Y-%m-%d"),
                end=current_end.strftime("%Y-%m-%d"),
                interval=interval,
                progress=False
            )
            if len(df) > 0:
                all_data.append(df)
                print(f"  Downloaded {len(df)} bars: {current_start.strftime('%Y-%m-%d')} → {current_end.strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"  Chunk failed: {e}")

        current_start = current_end

    if not all_data:
        print("ERROR: No data downloaded. Using generated sample data for demonstration.")
        return generate_sample_data(total_days)

    data = pd.concat(all_data)
    data = data[~data.index.duplicated(keep='first')]
    data.sort_index(inplace=True)

    # Flatten multi-level columns if present
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    print(f"Total bars downloaded: {len(data)}")
    print(f"Date range: {data.index[0]} → {data.index[-1]}")
    return data


def generate_sample_data(total_days):
    """Generate realistic GBP/JPY 5min sample data for backtesting."""
    print("Generating synthetic GBP/JPY data for backtesting...")

    bars_per_day = 288  # 24h * 60min / 5min
    total_bars = total_days * bars_per_day

    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=total_bars, freq="5min")

    # Start around 190.000 (realistic GBP/JPY level)
    price = 190.000
    opens, highs, lows, closes, volumes = [], [], [], [], []

    for i in range(total_bars):
        # Random walk with slight mean reversion
        change = np.random.normal(0, 0.015)  # ~1.5 pip avg move per 5min bar
        o = price
        c = price + change
        h = max(o, c) + abs(np.random.normal(0, 0.008))
        l = min(o, c) - abs(np.random.normal(0, 0.008))
        v = int(np.random.uniform(100, 5000))

        opens.append(round(o, 3))
        highs.append(round(h, 3))
        lows.append(round(l, 3))
        closes.append(round(c, 3))
        volumes.append(v)
        price = c

    data = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes
    }, index=dates)

    print(f"Generated {len(data)} bars")
    return data


# =============================================================================
# INDICATORS
# =============================================================================
def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def calculate_supertrend(df, period=10, multiplier=3.0):
    """Calculate Supertrend indicator."""
    hl2 = (df["High"] + df["Low"]) / 2

    # ATR
    tr1 = df["High"] - df["Low"]
    tr2 = abs(df["High"] - df["Close"].shift(1))
    tr3 = abs(df["Low"] - df["Close"].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    # Basic bands
    upper_basic = hl2 + (multiplier * atr)
    lower_basic = hl2 - (multiplier * atr)

    upper_band = upper_basic.copy()
    lower_band = lower_basic.copy()
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=float)

    for i in range(period, len(df)):
        # Upper band
        if upper_basic.iloc[i] < upper_band.iloc[i-1] or df["Close"].iloc[i-1] > upper_band.iloc[i-1]:
            upper_band.iloc[i] = upper_basic.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i-1]

        # Lower band
        if lower_basic.iloc[i] > lower_band.iloc[i-1] or df["Close"].iloc[i-1] < lower_band.iloc[i-1]:
            lower_band.iloc[i] = lower_basic.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i-1]

        # Supertrend
        if i == period:
            if df["Close"].iloc[i] <= upper_band.iloc[i]:
                direction.iloc[i] = 1   # bearish
                supertrend.iloc[i] = upper_band.iloc[i]
            else:
                direction.iloc[i] = -1  # bullish
                supertrend.iloc[i] = lower_band.iloc[i]
        else:
            prev_dir = direction.iloc[i-1]
            if prev_dir == -1:  # was bullish
                if df["Close"].iloc[i] < lower_band.iloc[i]:
                    direction.iloc[i] = 1   # flip to bearish
                    supertrend.iloc[i] = upper_band.iloc[i]
                else:
                    direction.iloc[i] = -1  # stay bullish
                    supertrend.iloc[i] = lower_band.iloc[i]
            else:  # was bearish
                if df["Close"].iloc[i] > upper_band.iloc[i]:
                    direction.iloc[i] = -1  # flip to bullish
                    supertrend.iloc[i] = lower_band.iloc[i]
                else:
                    direction.iloc[i] = 1   # stay bearish
                    supertrend.iloc[i] = upper_band.iloc[i]

    return supertrend, direction


# =============================================================================
# BACKTESTER
# =============================================================================
def run_backtest(data):
    """Run the EMA + Supertrend strategy backtest."""
    print("\nCalculating indicators...")

    df = data.copy()

    # EMAs
    df["EMA_Fast"] = calculate_ema(df["Close"], EMA_FAST)
    df["EMA_Slow"] = calculate_ema(df["Close"], EMA_SLOW)

    # Supertrend
    df["ST_Line"], df["ST_Dir"] = calculate_supertrend(df, ST_PERIOD, ST_MULTIPLIER)

    # Drop NaN rows (from indicator warmup)
    df.dropna(subset=["EMA_Fast", "EMA_Slow", "ST_Line", "ST_Dir"], inplace=True)

    # EMA crossover signals
    df["EMA_Bull_Cross"] = (df["EMA_Fast"] > df["EMA_Slow"]) & (df["EMA_Fast"].shift(1) <= df["EMA_Slow"].shift(1))
    df["EMA_Bear_Cross"] = (df["EMA_Fast"] < df["EMA_Slow"]) & (df["EMA_Fast"].shift(1) >= df["EMA_Slow"].shift(1))

    # Supertrend flip signals
    df["ST_Bullish"] = df["ST_Dir"] < 0
    df["ST_Bearish"] = df["ST_Dir"] > 0
    df["ST_Flip_Bull"] = df["ST_Bullish"] & ~df["ST_Bullish"].shift(1).fillna(False)
    df["ST_Flip_Bear"] = df["ST_Bearish"] & ~df["ST_Bearish"].shift(1).fillna(False)

    # Entry conditions
    df["Long_Entry"]  = df["EMA_Bull_Cross"] & df["ST_Bullish"]
    df["Short_Entry"] = df["EMA_Bear_Cross"] & df["ST_Bearish"]

    # Exit conditions
    df["Long_Exit"]  = df["ST_Flip_Bear"] | df["EMA_Bear_Cross"]
    df["Short_Exit"] = df["ST_Flip_Bull"] | df["EMA_Bull_Cross"]

    print("Running backtest simulation...")

    # Simulation state
    balance = INITIAL_BALANCE
    equity_curve = []
    trades = []
    position = None  # None, "long", or "short"
    entry_price = 0
    entry_time = None
    stop_loss = 0
    peak_balance = INITIAL_BALANCE
    max_drawdown = 0
    max_drawdown_pct = 0

    spread = SPREAD_POINTS * POINT_VALUE  # Convert to price units

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        current_time = df.index[i]
        close = row["Close"]
        high = row["High"]
        low = row["Low"]
        st_line = row["ST_Line"]

        # === CHECK STOP LOSS ===
        if position == "long":
            if low <= stop_loss:
                # Stopped out
                pnl_pips = (stop_loss - entry_price) / POINT_VALUE / 10  # pips
                pnl_usd = pnl_pips * LOT_SIZE * 100  # approx for JPY pairs
                balance += pnl_usd
                trades.append({
                    "type": "long", "entry_time": entry_time, "exit_time": current_time,
                    "entry_price": entry_price, "exit_price": stop_loss,
                    "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
                    "exit_reason": "Stop Loss"
                })
                position = None

        elif position == "short":
            if high >= stop_loss:
                # Stopped out
                pnl_pips = (entry_price - stop_loss) / POINT_VALUE / 10
                pnl_usd = pnl_pips * LOT_SIZE * 100
                balance += pnl_usd
                trades.append({
                    "type": "short", "entry_time": entry_time, "exit_time": current_time,
                    "entry_price": entry_price, "exit_price": stop_loss,
                    "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
                    "exit_reason": "Stop Loss"
                })
                position = None

        # === UPDATE TRAILING SL ===
        if position == "long":
            new_sl = st_line - SL_BUFFER
            if new_sl > stop_loss:
                stop_loss = new_sl

        elif position == "short":
            new_sl = st_line + SL_BUFFER
            if new_sl < stop_loss:
                stop_loss = new_sl

        # === CHECK SIGNAL EXIT ===
        if position == "long" and row["Long_Exit"]:
            pnl_pips = (close - entry_price - spread) / POINT_VALUE / 10
            pnl_usd = pnl_pips * LOT_SIZE * 100
            balance += pnl_usd
            trades.append({
                "type": "long", "entry_time": entry_time, "exit_time": current_time,
                "entry_price": entry_price, "exit_price": close,
                "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
                "exit_reason": "Signal (ST Flip / EMA Cross)"
            })
            position = None

        elif position == "short" and row["Short_Exit"]:
            pnl_pips = (entry_price - close - spread) / POINT_VALUE / 10
            pnl_usd = pnl_pips * LOT_SIZE * 100
            balance += pnl_usd
            trades.append({
                "type": "short", "entry_time": entry_time, "exit_time": current_time,
                "entry_price": entry_price, "exit_price": close,
                "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
                "exit_reason": "Signal (ST Flip / EMA Cross)"
            })
            position = None

        # === CHECK ENTRIES ===
        if position is None:
            if row["Long_Entry"]:
                entry_price = close + spread  # Buy at ask
                entry_time = current_time
                stop_loss = st_line - SL_BUFFER
                position = "long"

            elif row["Short_Entry"]:
                entry_price = close - spread  # Sell at bid
                entry_time = current_time
                stop_loss = st_line + SL_BUFFER
                position = "short"

        # Track equity
        equity_curve.append({"time": current_time, "balance": round(balance, 2)})

        # Track drawdown
        if balance > peak_balance:
            peak_balance = balance
        dd = peak_balance - balance
        dd_pct = (dd / peak_balance) * 100 if peak_balance > 0 else 0
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct
            max_drawdown = dd

    # Close any remaining position at end
    if position is not None:
        close = df.iloc[-1]["Close"]
        if position == "long":
            pnl_pips = (close - entry_price - spread) / POINT_VALUE / 10
        else:
            pnl_pips = (entry_price - close - spread) / POINT_VALUE / 10
        pnl_usd = pnl_pips * LOT_SIZE * 100
        balance += pnl_usd
        trades.append({
            "type": position, "entry_time": entry_time, "exit_time": df.index[-1],
            "entry_price": entry_price, "exit_price": close,
            "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
            "exit_reason": "End of Backtest"
        })

    return trades, equity_curve, balance, max_drawdown, max_drawdown_pct, df


# =============================================================================
# REPORT GENERATION
# =============================================================================
def generate_report(trades, equity_curve, final_balance, max_dd, max_dd_pct, df, output_dir):
    """Generate backtest report with statistics and charts."""

    os.makedirs(output_dir, exist_ok=True)

    # === STATISTICS ===
    total_trades = len(trades)
    if total_trades == 0:
        print("No trades generated!")
        return

    winners = [t for t in trades if t["pnl_usd"] > 0]
    losers  = [t for t in trades if t["pnl_usd"] <= 0]
    longs   = [t for t in trades if t["type"] == "long"]
    shorts  = [t for t in trades if t["type"] == "short"]

    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_pips = sum(t["pnl_pips"] for t in trades)

    win_rate = (len(winners) / total_trades) * 100
    avg_win = np.mean([t["pnl_usd"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_usd"] for t in losers]) if losers else 0

    gross_profit = sum(t["pnl_usd"] for t in winners) if winners else 0
    gross_loss   = abs(sum(t["pnl_usd"] for t in losers)) if losers else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Sharpe Ratio (annualized, assuming 252 trading days)
    returns = [t["pnl_usd"] for t in trades]
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = (np.mean(returns) / np.std(returns)) * math.sqrt(252)
    else:
        sharpe = 0

    # Expectancy
    expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)

    # Duration stats
    durations = []
    for t in trades:
        if isinstance(t["entry_time"], pd.Timestamp) and isinstance(t["exit_time"], pd.Timestamp):
            dur = (t["exit_time"] - t["entry_time"]).total_seconds() / 60
            durations.append(dur)

    avg_duration = np.mean(durations) if durations else 0

    # Monthly P/L
    monthly_pnl = {}
    for t in trades:
        month_key = t["exit_time"].strftime("%Y-%m") if isinstance(t["exit_time"], pd.Timestamp) else "Unknown"
        if month_key not in monthly_pnl:
            monthly_pnl[month_key] = 0
        monthly_pnl[month_key] += t["pnl_usd"]

    # === PRINT REPORT ===
    report_lines = []
    report_lines.append("=" * 65)
    report_lines.append("  EMA 9/26 + SUPERTREND STRATEGY — BACKTEST REPORT")
    report_lines.append("=" * 65)
    report_lines.append(f"  Pair:              GBP/JPY")
    report_lines.append(f"  Timeframe:         5 Minutes")
    report_lines.append(f"  Period:            {df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}")
    report_lines.append(f"  Initial Balance:   ${INITIAL_BALANCE:,.2f}")
    report_lines.append(f"  Lot Size:          {LOT_SIZE}")
    report_lines.append(f"  Spread:            {SPREAD_POINTS} points (~{SPREAD_POINTS/10:.1f} pips)")
    report_lines.append("")
    report_lines.append("-" * 65)
    report_lines.append("  PERFORMANCE SUMMARY")
    report_lines.append("-" * 65)
    report_lines.append(f"  Final Balance:     ${final_balance:,.2f}")
    report_lines.append(f"  Net P/L:           ${total_pnl:,.2f} ({(total_pnl/INITIAL_BALANCE)*100:.2f}%)")
    report_lines.append(f"  Net Pips:          {total_pips:,.1f}")
    report_lines.append(f"  Max Drawdown:      ${max_dd:,.2f} ({max_dd_pct:.2f}%)")
    report_lines.append("")
    report_lines.append("-" * 65)
    report_lines.append("  TRADE STATISTICS")
    report_lines.append("-" * 65)
    report_lines.append(f"  Total Trades:      {total_trades}")
    report_lines.append(f"  Long Trades:       {len(longs)}")
    report_lines.append(f"  Short Trades:      {len(shorts)}")
    report_lines.append(f"  Winners:           {len(winners)} ({win_rate:.1f}%)")
    report_lines.append(f"  Losers:            {len(losers)} ({100-win_rate:.1f}%)")
    report_lines.append(f"  Avg Win:           ${avg_win:,.2f}")
    report_lines.append(f"  Avg Loss:          ${avg_loss:,.2f}")
    report_lines.append(f"  Profit Factor:     {profit_factor:.2f}")
    report_lines.append(f"  Sharpe Ratio:      {sharpe:.2f}")
    report_lines.append(f"  Expectancy:        ${expectancy:,.2f} per trade")
    report_lines.append(f"  Avg Trade Duration: {avg_duration:.0f} minutes ({avg_duration/60:.1f} hours)")
    report_lines.append("")
    report_lines.append("-" * 65)
    report_lines.append("  MONTHLY P/L")
    report_lines.append("-" * 65)

    for month, pnl in sorted(monthly_pnl.items()):
        bar = "+" * max(1, int(abs(pnl) / 5)) if pnl > 0 else "-" * max(1, int(abs(pnl) / 5))
        report_lines.append(f"  {month}:  ${pnl:>10,.2f}  {bar}")

    report_lines.append("")
    report_lines.append("-" * 65)
    report_lines.append("  EXIT REASON BREAKDOWN")
    report_lines.append("-" * 65)
    exit_reasons = {}
    for t in trades:
        r = t["exit_reason"]
        if r not in exit_reasons:
            exit_reasons[r] = {"count": 0, "pnl": 0}
        exit_reasons[r]["count"] += 1
        exit_reasons[r]["pnl"] += t["pnl_usd"]

    for reason, data in exit_reasons.items():
        report_lines.append(f"  {reason}: {data['count']} trades, ${data['pnl']:,.2f}")

    report_lines.append("")
    report_lines.append("=" * 65)

    report_text = "\n".join(report_lines)
    print(report_text)

    # Save text report
    with open(os.path.join(output_dir, "backtest_report.txt"), "w") as f:
        f.write(report_text)

    # === SAVE TRADE LOG ===
    trades_df = pd.DataFrame(trades)
    trades_df.to_csv(os.path.join(output_dir, "trade_log.csv"), index=False)

    # === GENERATE CHARTS ===
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        # 1. Equity Curve
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), gridspec_kw={'height_ratios': [3, 1, 1]})
        fig.suptitle("EMA 9/26 + Supertrend Strategy — GBP/JPY 5min Backtest", fontsize=14, fontweight='bold')

        eq_df = pd.DataFrame(equity_curve)
        eq_df["time"] = pd.to_datetime(eq_df["time"])

        # Equity curve
        ax1 = axes[0]
        ax1.plot(eq_df["time"], eq_df["balance"], color="#2196F3", linewidth=1)
        ax1.axhline(y=INITIAL_BALANCE, color="gray", linestyle="--", alpha=0.5)
        ax1.fill_between(eq_df["time"], INITIAL_BALANCE, eq_df["balance"],
                         where=(eq_df["balance"] >= INITIAL_BALANCE), alpha=0.15, color="green")
        ax1.fill_between(eq_df["time"], INITIAL_BALANCE, eq_df["balance"],
                         where=(eq_df["balance"] < INITIAL_BALANCE), alpha=0.15, color="red")
        ax1.set_ylabel("Balance ($)")
        ax1.set_title("Equity Curve")
        ax1.grid(True, alpha=0.3)

        # Monthly P/L bars
        ax2 = axes[1]
        months = sorted(monthly_pnl.keys())
        values = [monthly_pnl[m] for m in months]
        colors = ["green" if v > 0 else "red" for v in values]
        ax2.bar(range(len(months)), values, color=colors, alpha=0.7)
        ax2.set_xticks(range(len(months)))
        ax2.set_xticklabels(months, rotation=45, fontsize=7)
        ax2.set_ylabel("P/L ($)")
        ax2.set_title("Monthly P/L")
        ax2.axhline(y=0, color="gray", linewidth=0.5)
        ax2.grid(True, alpha=0.3)

        # Win/Loss distribution
        ax3 = axes[2]
        pnl_values = [t["pnl_usd"] for t in trades]
        ax3.hist(pnl_values, bins=40, color="#2196F3", alpha=0.7, edgecolor="white")
        ax3.axvline(x=0, color="red", linewidth=1, linestyle="--")
        ax3.set_xlabel("Trade P/L ($)")
        ax3.set_ylabel("Frequency")
        ax3.set_title("P/L Distribution")
        ax3.grid(True, alpha=0.3)

        plt.tight_layout()
        chart_path = os.path.join(output_dir, "backtest_chart.png")
        plt.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"\nChart saved: {chart_path}")

    except ImportError:
        print("matplotlib not available, skipping chart generation")

    # Save summary JSON
    summary = {
        "pair": "GBP/JPY",
        "timeframe": "5min",
        "period": f"{df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}",
        "initial_balance": INITIAL_BALANCE,
        "final_balance": round(final_balance, 2),
        "net_pnl": round(total_pnl, 2),
        "net_pnl_pct": round((total_pnl/INITIAL_BALANCE)*100, 2),
        "net_pips": round(total_pips, 1),
        "max_drawdown_usd": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "total_trades": total_trades,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 2),
        "expectancy_per_trade": round(expectancy, 2),
        "avg_trade_duration_min": round(avg_duration, 0)
    }

    with open(os.path.join(output_dir, "backtest_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nAll reports saved to: {output_dir}/")
    return summary


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

    # Download/generate data
    data = download_data("GBPJPY=X", period_years=2, interval="5m")

    # Run backtest
    trades, equity_curve, final_balance, max_dd, max_dd_pct, df = run_backtest(data)

    # Generate report
    summary = generate_report(trades, equity_curve, final_balance, max_dd, max_dd_pct, df, output_dir)

    if summary:
        print("\n" + "=" * 50)
        print("BACKTEST COMPLETE")
        print(f"Net P/L: ${summary['net_pnl']:,.2f} ({summary['net_pnl_pct']:.2f}%)")
        print(f"Max Drawdown: {summary['max_drawdown_pct']:.2f}%")
        print(f"Win Rate: {summary['win_rate']:.1f}%")
        print(f"Profit Factor: {summary['profit_factor']:.2f}")
        print("=" * 50)
