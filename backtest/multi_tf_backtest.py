"""
Multi-timeframe backtest: 5min (recent), 15min (~6 months), 1h (2 years)
Uses the same EMA 9/26 + Supertrend strategy across all three.
"""

import os
import sys
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Add parent for shared code
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtester import (
    calculate_ema, calculate_supertrend, generate_report,
    EMA_FAST, EMA_SLOW, ST_PERIOD, ST_MULTIPLIER, SL_BUFFER,
    LOT_SIZE, POINT_VALUE, INITIAL_BALANCE, SPREAD_POINTS
)

import yfinance as yf


def download_tf_data(symbol, interval, period_str):
    """Download data for a specific timeframe."""
    print(f"\nDownloading {symbol} {interval} data (period={period_str})...")
    try:
        df = yf.download(symbol, period=period_str, interval=interval, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        print(f"  Got {len(df)} bars: {df.index[0]} → {df.index[-1]}")
        return df
    except Exception as e:
        print(f"  Failed: {e}")
        return None


def run_backtest_on_data(data):
    """Run backtest on given data, return trades and stats."""
    df = data.copy()
    df["EMA_Fast"] = calculate_ema(df["Close"], EMA_FAST)
    df["EMA_Slow"] = calculate_ema(df["Close"], EMA_SLOW)
    df["ST_Line"], df["ST_Dir"] = calculate_supertrend(df, ST_PERIOD, ST_MULTIPLIER)
    df.dropna(subset=["EMA_Fast", "EMA_Slow", "ST_Line", "ST_Dir"], inplace=True)

    df["EMA_Bull_Cross"] = (df["EMA_Fast"] > df["EMA_Slow"]) & (df["EMA_Fast"].shift(1) <= df["EMA_Slow"].shift(1))
    df["EMA_Bear_Cross"] = (df["EMA_Fast"] < df["EMA_Slow"]) & (df["EMA_Fast"].shift(1) >= df["EMA_Slow"].shift(1))
    df["ST_Bullish"] = df["ST_Dir"] < 0
    df["ST_Bearish"] = df["ST_Dir"] > 0
    df["ST_Flip_Bull"] = df["ST_Bullish"] & ~df["ST_Bullish"].shift(1).fillna(False)
    df["ST_Flip_Bear"] = df["ST_Bearish"] & ~df["ST_Bearish"].shift(1).fillna(False)

    df["Long_Entry"]  = df["EMA_Bull_Cross"] & df["ST_Bullish"]
    df["Short_Entry"] = df["EMA_Bear_Cross"] & df["ST_Bearish"]
    df["Long_Exit"]  = df["ST_Flip_Bear"] | df["EMA_Bear_Cross"]
    df["Short_Exit"] = df["ST_Flip_Bull"] | df["EMA_Bull_Cross"]

    spread = SPREAD_POINTS * POINT_VALUE
    balance = INITIAL_BALANCE
    trades = []
    equity_curve = []
    position = None
    entry_price = 0
    entry_time = None
    stop_loss = 0
    peak_balance = INITIAL_BALANCE
    max_drawdown = 0
    max_drawdown_pct = 0

    for i in range(1, len(df)):
        row = df.iloc[i]
        current_time = df.index[i]
        close = row["Close"]
        high = row["High"]
        low = row["Low"]
        st_line = row["ST_Line"]

        if position == "long" and low <= stop_loss:
            pnl_pips = (stop_loss - entry_price) / POINT_VALUE / 10
            pnl_usd = pnl_pips * LOT_SIZE * 100
            balance += pnl_usd
            trades.append({"type": "long", "entry_time": entry_time, "exit_time": current_time,
                           "entry_price": entry_price, "exit_price": stop_loss,
                           "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2), "exit_reason": "Stop Loss"})
            position = None
        elif position == "short" and high >= stop_loss:
            pnl_pips = (entry_price - stop_loss) / POINT_VALUE / 10
            pnl_usd = pnl_pips * LOT_SIZE * 100
            balance += pnl_usd
            trades.append({"type": "short", "entry_time": entry_time, "exit_time": current_time,
                           "entry_price": entry_price, "exit_price": stop_loss,
                           "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2), "exit_reason": "Stop Loss"})
            position = None

        if position == "long":
            new_sl = st_line - SL_BUFFER
            if new_sl > stop_loss: stop_loss = new_sl
        elif position == "short":
            new_sl = st_line + SL_BUFFER
            if new_sl < stop_loss: stop_loss = new_sl

        if position == "long" and row["Long_Exit"]:
            pnl_pips = (close - entry_price - spread) / POINT_VALUE / 10
            pnl_usd = pnl_pips * LOT_SIZE * 100
            balance += pnl_usd
            trades.append({"type": "long", "entry_time": entry_time, "exit_time": current_time,
                           "entry_price": entry_price, "exit_price": close,
                           "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
                           "exit_reason": "Signal (ST Flip / EMA Cross)"})
            position = None
        elif position == "short" and row["Short_Exit"]:
            pnl_pips = (entry_price - close - spread) / POINT_VALUE / 10
            pnl_usd = pnl_pips * LOT_SIZE * 100
            balance += pnl_usd
            trades.append({"type": "short", "entry_time": entry_time, "exit_time": current_time,
                           "entry_price": entry_price, "exit_price": close,
                           "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2),
                           "exit_reason": "Signal (ST Flip / EMA Cross)"})
            position = None

        if position is None:
            if row["Long_Entry"]:
                entry_price = close + spread
                entry_time = current_time
                stop_loss = st_line - SL_BUFFER
                position = "long"
            elif row["Short_Entry"]:
                entry_price = close - spread
                entry_time = current_time
                stop_loss = st_line + SL_BUFFER
                position = "short"

        equity_curve.append({"time": current_time, "balance": round(balance, 2)})
        if balance > peak_balance: peak_balance = balance
        dd = peak_balance - balance
        dd_pct = (dd / peak_balance) * 100 if peak_balance > 0 else 0
        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct
            max_drawdown = dd

    if position is not None:
        close = df.iloc[-1]["Close"]
        pnl_pips = ((close - entry_price - spread) if position == "long" else (entry_price - close - spread)) / POINT_VALUE / 10
        pnl_usd = pnl_pips * LOT_SIZE * 100
        balance += pnl_usd
        trades.append({"type": position, "entry_time": entry_time, "exit_time": df.index[-1],
                       "entry_price": entry_price, "exit_price": close,
                       "pnl_pips": round(pnl_pips, 1), "pnl_usd": round(pnl_usd, 2), "exit_reason": "End of Backtest"})

    return trades, equity_curve, balance, max_drawdown, max_drawdown_pct, df


def calc_stats(trades):
    """Calculate summary statistics."""
    if not trades:
        return {}
    total = len(trades)
    winners = [t for t in trades if t["pnl_usd"] > 0]
    losers  = [t for t in trades if t["pnl_usd"] <= 0]
    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_pips = sum(t["pnl_pips"] for t in trades)
    win_rate = (len(winners) / total) * 100
    gross_profit = sum(t["pnl_usd"] for t in winners) if winners else 0
    gross_loss = abs(sum(t["pnl_usd"] for t in losers)) if losers else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    avg_win = np.mean([t["pnl_usd"] for t in winners]) if winners else 0
    avg_loss = np.mean([t["pnl_usd"] for t in losers]) if losers else 0
    returns = [t["pnl_usd"] for t in trades]
    sharpe = (np.mean(returns) / np.std(returns)) * math.sqrt(252) if len(returns) > 1 and np.std(returns) > 0 else 0
    expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)
    return {
        "total_trades": total, "winners": len(winners), "losers": len(losers),
        "win_rate": round(win_rate, 1), "net_pnl": round(total_pnl, 2),
        "net_pips": round(total_pips, 1), "profit_factor": round(pf, 2),
        "sharpe": round(sharpe, 2), "expectancy": round(expectancy, 2),
        "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2)
    }


if __name__ == "__main__":
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(output_dir, exist_ok=True)

    symbol = "GBPJPY=X"

    # Download data for three timeframes
    # 1h: up to 2 years (730d)
    # 15m: up to ~60 days
    # 5m: up to ~60 days
    timeframes = {
        "1h": {"interval": "1h", "period": "2y", "label": "1 Hour"},
        "15m": {"interval": "15m", "period": "60d", "label": "15 Minutes"},
        "5m": {"interval": "5m", "period": "60d", "label": "5 Minutes"},
    }

    results = {}
    all_details = {}

    for tf_key, tf_info in timeframes.items():
        data = download_tf_data(symbol, tf_info["interval"], tf_info["period"])
        if data is None or len(data) < 50:
            print(f"  Skipping {tf_key}: insufficient data")
            continue

        trades, eq, final_bal, max_dd, max_dd_pct, df = run_backtest_on_data(data)
        stats = calc_stats(trades)
        stats["final_balance"] = round(final_bal, 2)
        stats["max_drawdown_pct"] = round(max_dd_pct, 2)
        stats["max_drawdown_usd"] = round(max_dd, 2)
        stats["period"] = f"{df.index[0].strftime('%Y-%m-%d')} → {df.index[-1].strftime('%Y-%m-%d')}"
        stats["bars"] = len(df)
        results[tf_key] = stats
        all_details[tf_key] = {"trades": trades, "equity": eq, "df": df}

        # Generate individual report
        generate_report(trades, eq, final_bal, max_dd, max_dd_pct, df,
                        os.path.join(output_dir, f"tf_{tf_key}"))

    # Print multi-TF comparison
    print("\n" + "=" * 80)
    print("  MULTI-TIMEFRAME COMPARISON — EMA 9/26 + Supertrend Strategy on GBP/JPY")
    print("=" * 80)
    print(f"{'Metric':<25} {'5 min':<20} {'15 min':<20} {'1 hour':<20}")
    print("-" * 80)

    metrics = [
        ("Period", "period"),
        ("Bars", "bars"),
        ("Total Trades", "total_trades"),
        ("Win Rate (%)", "win_rate"),
        ("Net P/L ($)", "net_pnl"),
        ("Net Pips", "net_pips"),
        ("Profit Factor", "profit_factor"),
        ("Sharpe Ratio", "sharpe"),
        ("Expectancy ($/trade)", "expectancy"),
        ("Max Drawdown (%)", "max_drawdown_pct"),
        ("Avg Win ($)", "avg_win"),
        ("Avg Loss ($)", "avg_loss"),
    ]

    comparison_lines = []
    for label, key in metrics:
        row = f"{label:<25}"
        for tf in ["5m", "15m", "1h"]:
            if tf in results:
                val = results[tf].get(key, "N/A")
                row += f" {str(val):<19}"
            else:
                row += f" {'N/A':<19}"
        print(row)
        comparison_lines.append(row)

    print("=" * 80)

    # Save comparison
    with open(os.path.join(output_dir, "multi_tf_comparison.json"), "w") as f:
        json.dump(results, f, indent=2)

    comparison_text = "\n".join([
        "=" * 80,
        "  MULTI-TIMEFRAME COMPARISON — EMA 9/26 + Supertrend Strategy on GBP/JPY",
        "=" * 80,
        f"{'Metric':<25} {'5 min':<20} {'15 min':<20} {'1 hour':<20}",
        "-" * 80
    ] + comparison_lines + ["=" * 80])

    with open(os.path.join(output_dir, "multi_tf_comparison.txt"), "w") as f:
        f.write(comparison_text)

    # Generate combined chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        fig.suptitle("EMA 9/26 + Supertrend — Multi-Timeframe Equity Curves (GBP/JPY)", fontsize=13, fontweight='bold')

        for idx, (tf_key, tf_label) in enumerate([("5m", "5 min"), ("15m", "15 min"), ("1h", "1 Hour")]):
            ax = axes[idx]
            if tf_key in all_details:
                eq = all_details[tf_key]["equity"]
                eq_df = pd.DataFrame(eq)
                eq_df["time"] = pd.to_datetime(eq_df["time"])
                ax.plot(eq_df["time"], eq_df["balance"], color="#2196F3", linewidth=1)
                ax.axhline(y=INITIAL_BALANCE, color="gray", linestyle="--", alpha=0.5)
                ax.fill_between(eq_df["time"], INITIAL_BALANCE, eq_df["balance"],
                                where=(eq_df["balance"] >= INITIAL_BALANCE), alpha=0.15, color="green")
                ax.fill_between(eq_df["time"], INITIAL_BALANCE, eq_df["balance"],
                                where=(eq_df["balance"] < INITIAL_BALANCE), alpha=0.15, color="red")

                stats = results[tf_key]
                info = f"P/L: ${stats['net_pnl']} | WR: {stats['win_rate']}% | PF: {stats['profit_factor']}"
                ax.set_title(f"{tf_label}\n{info}", fontsize=10)
            else:
                ax.text(0.5, 0.5, "No Data", ha='center', va='center', transform=ax.transAxes)
                ax.set_title(tf_label)

            ax.set_ylabel("Balance ($)")
            ax.grid(True, alpha=0.3)
            ax.tick_params(axis='x', rotation=30, labelsize=7)

        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "multi_tf_chart.png"), dpi=150, bbox_inches="tight")
        plt.close()
        print(f"\nMulti-TF chart saved: {output_dir}/multi_tf_chart.png")
    except ImportError:
        pass

    print("\nDone!")
