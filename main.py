#!/usr/bin/env python3
"""
Crypto Price Tracker - main.py

Features:
- Polls CoinGecko simple price API for selected coins (no API key required)
- Logs prices to CSV
- Threshold alerts (console or Telegram)
- Portfolio value calculation
- Save simple matplotlib plots of recent history
"""

import argparse
import csv
import datetime
import os
import sys
import time
from typing import Dict, List, Optional

import requests
import matplotlib.pyplot as plt  # matplotlib required
import pandas as pd  # pandas required

# -------------------------
# Configuration & helpers
# -------------------------
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "ADA": "cardano",
    "SOL": "solana",
    "XRP": "ripple",
    "DOT": "polkadot",
    "DOGE": "dogecoin",
    # add more as needed
}

COINGECKO_SIMPLE_PRICE = "https://api.coingecko.com/api/v3/simple/price"

def to_id(symbol: str) -> str:
    symbol = symbol.upper()
    return COINGECKO_IDS.get(symbol, symbol.lower())

def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat() + "Z"



# -------------------------
# Core tracker
# -------------------------
class CryptoTracker:
    def __init__(self,
                 symbols: List[str],
                 vs_currency: str = "usd",
                 csv_path: Optional[str] = None):
        self.symbols = [s.upper() for s in symbols]
        self.ids = [to_id(s) for s in self.symbols]
        self.vs_currency = vs_currency
        self.csv_path = csv_path
        if csv_path:
            self._ensure_csv()

    def _ensure_csv(self):
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                header = ["timestamp"] + [f"{s}_{self.vs_currency}" for s in self.symbols]
                writer.writerow(header)

    def fetch_prices(self) -> Dict[str, float]:
        ids_param = ",".join(self.ids)
        params = {"ids": ids_param, "vs_currencies": self.vs_currency}
        resp = requests.get(COINGECKO_SIMPLE_PRICE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        out = {}
        for sym, idx in zip(self.symbols, self.ids):
            price = data.get(idx, {}).get(self.vs_currency)
            out[sym] = float(price) if price is not None else None
        return out

    def log(self, prices: Dict[str, float]):
        if not self.csv_path:
            return
        row = [now_iso()] + [prices.get(s) for s in self.symbols]
        with open(self.csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

# -------------------------
# Alerts & Notifications
# -------------------------
class AlertManager:
    def __init__(self, thresholds: Dict[str, float] = None, telegram_token: str = None, telegram_chat_id: str = None):
        # thresholds e.g. {"BTC": 60000} will alert when price <= threshold
        self.thresholds = {k.upper(): v for k, v in (thresholds or {}).items()}
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id

    def check(self, prices: Dict[str, float]) -> List[str]:
        messages = []
        for sym, price in prices.items():
            if price is None:
                continue
            thr = self.thresholds.get(sym)
            if thr is not None:
                # trigger if price crosses below threshold
                if price <= thr:
                    msg = f"ALERT: {sym} price {price} <= threshold {thr}"
                    messages.append(msg)
        return messages

    def send_telegram(self, messages: List[str]):
        if not (self.telegram_token and self.telegram_chat_id):
            return
        for msg in messages:
            try:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                requests.post(url, data={"chat_id": self.telegram_chat_id, "text": msg}, timeout=10)
            except Exception as e:
                print("Failed to send telegram:", e)

# -------------------------
# Utilities: plotting & portfolio
# -------------------------
def plot_from_csv(csv_path: str, symbol: str, output_png: str = None, last_n: int = 100):
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    if f"{symbol}_usd" not in df.columns and f"{symbol}_USD" in df.columns:
        col = f"{symbol}_USD"
    else:
        col = f"{symbol}_usd"
    if col not in df.columns:
        # try upper-case header created by our writer
        alt = f"{symbol}_usd".upper()
        if alt in df.columns:
            col = alt
    if col not in df.columns:
        # fallback: find column by prefix
        candidates = [c for c in df.columns if c.lower().startswith(symbol.lower()+"_")]
        if candidates:
            col = candidates[0]
        else:
            raise ValueError(f"Symbol column for {symbol} not found in {csv_path}")

    series = df[[ "timestamp", col ]].dropna().tail(last_n)
    series = series.set_index("timestamp")
    ax = series.plot(title=f"{symbol} price (last {len(series)} samples)")
    ax.set_xlabel("timestamp")
    ax.set_ylabel("price")
    plt.tight_layout()

    out = output_png or f"{symbol.lower()}_history.png"
    plt.savefig(out)
    plt.close()
    return out

def portfolio_value(prices: Dict[str, float], holdings: Dict[str, float]) -> float:
    total = 0.0
    for sym, qty in holdings.items():
        p = prices.get(sym.upper())
        if p is None:
            continue
        total += p * qty
    return total

# -------------------------
# CLI & runner
# -------------------------
def parse_thresholds(texts: List[str]) -> Dict[str, float]:
    out = {}
    for t in texts or []:
        if ":" not in t:
            continue
        sym, val = t.split(":", 1)
        try:
            out[sym.strip().upper()] = float(val.strip())
        except:
            pass
    return out

def parse_holdings(texts: List[str]) -> Dict[str, float]:
    out = {}
    for t in texts or []:
        if ":" not in t:
            continue
        sym, val = t.split(":", 1)
        try:
            out[sym.strip().upper()] = float(val.strip())
        except:
            pass
    return out

def main():
    parser = argparse.ArgumentParser(description="Crypto Price Tracker")
    parser.add_argument("--symbols", "-s", nargs="+", default=["BTC","ETH"], help="Symbols e.g. BTC ETH")
    parser.add_argument("--interval", "-i", type=int, default=15, help="Polling interval seconds")
    parser.add_argument("--csv", "-c", default="prices.csv", help="CSV log path (set empty to disable)")
    parser.add_argument("--threshold", "-t", action="append", help="Threshold alert: SYMBOL:PRICE  e.g. BTC:60000")
    parser.add_argument("--holdings", "-H", action="append", help="Holdings for portfolio: SYMBOL:AMOUNT e.g. BTC:0.5")
    parser.add_argument("--plot", "-p", action="store_true", help="Generate PNG plots from CSV on exit (per symbol)")
    parser.add_argument("--run-once", action="store_true", help="Fetch once and exit")
    parser.add_argument("--telegram-token", help="Telegram bot token for alerts")
    parser.add_argument("--telegram-chat-id", help="Telegram chat id for alerts")
    args = parser.parse_args()

    csv_path = args.csv if args.csv else None
    tracker = CryptoTracker(symbols=args.symbols, csv_path=csv_path)
    thresholds = parse_thresholds(args.threshold)
    holdings = parse_holdings(args.holdings)
    alerts = AlertManager(thresholds=thresholds, telegram_token=args.telegram_token, telegram_chat_id=args.telegram_chat_id)

    print("Tracking:", ", ".join(tracker.symbols))
    try:
        while True:
            try:
                prices = tracker.fetch_prices()
            except Exception as e:
                print("Fetch failed:", e)
                prices = {s: None for s in tracker.symbols}

            ts = now_iso()
            display = " | ".join([f"{s}: {prices.get(s, 'N/A')}" for s in tracker.symbols])
            print(f"[{ts}] {display}")

            if csv_path:
                tracker.log(prices)

            msgs = alerts.check(prices)
            if msgs:
                for m in msgs:
                    print(m)
                alerts.send_telegram(msgs)

            if holdings:
                val = portfolio_value(prices, holdings)
                print(f"PORTFOLIO VALUE: {val:.2f} {tracker.vs_currency.upper()}")

            if args.run_once:
                break

            # Add sleep here
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

    if args.plot and csv_path:
        for s in tracker.symbols:
            try:
                out = plot_from_csv(csv_path, s)
                print("Saved plot:", out)
            except Exception as e:
                print("Plot failed for", s, e)

if __name__ == "__main__":
    main()
