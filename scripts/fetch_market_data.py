#!/usr/bin/env python3
"""
Usage:
  python scripts/fetch_market_data.py --ticker NVDA --type technical --date 2026-05-02
  python scripts/fetch_market_data.py --ticker NVDA --type news --date 2026-05-02
  python scripts/fetch_market_data.py --ticker NVDA --type fundamentals --date 2026-05-02
"""
import argparse
import json
import math
import sys
from datetime import date, timedelta

import yfinance as yf
import pandas as pd


def _safe(val):
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 2)
    except (TypeError, ValueError):
        return None


def fetch_technical(ticker: str, as_of: date) -> dict:
    end = as_of + timedelta(days=1)
    start = as_of - timedelta(days=520)
    tk = yf.Ticker(ticker)
    hist = tk.history(start=start.isoformat(), end=end.isoformat())
    if hist.empty:
        return {"error": f"No price data for {ticker}"}

    close = hist["Close"]
    volume = hist["Volume"]

    ema10 = close.ewm(span=10).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(100)

    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    boll_upper = sma20 + 2 * std20
    boll_lower = sma20 - 2 * std20

    atr_high = hist["High"]
    atr_low = hist["Low"]
    tr = pd.concat([
        atr_high - atr_low,
        (atr_high - close.shift()).abs(),
        (atr_low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    last = hist.index[-1].date().isoformat()
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else None

    return {
        "ticker": ticker,
        "as_of": as_of.isoformat(),
        "last_trading_day": last,
        "price": {
            "current": _safe(close.iloc[-1]),
            "prev_close": _safe(prev_close) if prev_close is not None else None,
            "change_pct": _safe((float(close.iloc[-1]) / prev_close - 1) * 100) if prev_close is not None and prev_close != 0 else None,
            "52w_high": _safe(close.rolling(252).max().iloc[-1]),
            "52w_low": _safe(close.rolling(252).min().iloc[-1]),
        },
        "indicators": {
            "ema10": _safe(ema10.iloc[-1]),
            "sma50": _safe(sma50.iloc[-1]),
            "sma200": _safe(sma200.iloc[-1]),
            "rsi14": _safe(rsi.iloc[-1]),
            "macd": _safe(macd.iloc[-1]),
            "macd_signal": _safe(signal.iloc[-1]),
            "macd_hist": _safe(macd.iloc[-1] - signal.iloc[-1]),
            "boll_upper": _safe(boll_upper.iloc[-1]),
            "boll_mid": _safe(sma20.iloc[-1]),
            "boll_lower": _safe(boll_lower.iloc[-1]),
            "atr14": _safe(atr.iloc[-1]),
        },
        "recent_closes": {
            row.date().isoformat(): _safe(val)
            for row, val in close.tail(10).items()
        },
    }


def fetch_news(ticker: str, as_of: date) -> dict:
    # yfinance always returns latest news regardless of as_of date
    tk = yf.Ticker(ticker)
    news = tk.news or []

    items = []
    for n in news[:15]:
        items.append({
            "title": n.get("content", {}).get("title", n.get("title", "")),
            "summary": n.get("content", {}).get("summary", ""),
            "publisher": n.get("content", {}).get("provider", {}).get("displayName", ""),
        })

    return {
        "ticker": ticker,
        "as_of": as_of.isoformat(),
        "news_count": len(items),
        "items": items,
    }


def fetch_macro(as_of: date) -> dict:
    # Pull news from broad market proxies to get global macro context
    macro_tickers = {
        "^GSPC": "S&P 500",
        "^TNX": "10Y Treasury Yield",
        "GC=F": "Gold Futures",
        "CL=F": "Crude Oil Futures",
    }
    items = []
    seen = set()
    for sym, label in macro_tickers.items():
        try:
            news = yf.Ticker(sym).news or []
            for n in news[:5]:
                title = n.get("content", {}).get("title", n.get("title", ""))
                if title and title not in seen:
                    seen.add(title)
                    items.append({
                        "source": label,
                        "title": title,
                        "summary": n.get("content", {}).get("summary", ""),
                        "publisher": n.get("content", {}).get("provider", {}).get("displayName", ""),
                    })
        except Exception:
            continue

    return {
        "as_of": as_of.isoformat(),
        "macro_news_count": len(items),
        "items": items[:20],
    }


def fetch_fundamentals(ticker: str, as_of: date) -> dict:
    tk = yf.Ticker(ticker)
    info = tk.info or {}

    keys = [
        "marketCap", "trailingPE", "forwardPE", "priceToBook",
        "revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins",
        "profitMargins", "returnOnEquity", "returnOnAssets",
        "totalRevenue", "totalCash", "totalDebt", "freeCashflow",
        "dividendYield", "beta", "shortRatio",
        "recommendationMean", "numberOfAnalystOpinions",
        "targetMeanPrice", "targetHighPrice", "targetLowPrice",
        "sector", "industry", "longBusinessSummary",
    ]
    data = {k: info.get(k) for k in keys}
    data["ticker"] = ticker
    data["as_of"] = as_of.isoformat()
    for k in list(data.keys()):
        if isinstance(data[k], float):
            data[k] = _safe(data[k])
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--type", required=True, choices=["technical", "news", "fundamentals", "macro"])
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    as_of = date.fromisoformat(args.date)
    fetchers = {
        "technical": fetch_technical,
        "news": fetch_news,
        "fundamentals": fetch_fundamentals,
        "macro": lambda ticker, as_of: fetch_macro(as_of),
    }

    try:
        result = fetchers[args.type](args.ticker, as_of)
    except Exception as e:
        result = {"error": str(e), "ticker": args.ticker, "type": args.type}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
