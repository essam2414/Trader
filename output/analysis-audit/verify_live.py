"""Read-only numerical audit. No app lifespan, server, stream, or DB writes."""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(Path(__file__).parent / "deps")]

import numpy as np
import talib

from app.alpaca_market_data import NEW_YORK, AlpacaMarketDataClient
from app.config import settings
from app.db import SessionLocal
from app.models import WatchlistEntry
from app.services.stock_analysis import daily_indicators
from app.services.stock_analysis_data import StockAnalysisService, analysis_window


def main():
    now = datetime.now(timezone.utc)
    service = StockAnalysisService(
        AlpacaMarketDataClient(settings.alpaca_api_key, settings.alpaca_api_secret, "sip"), SessionLocal
    )
    with SessionLocal() as db:
        entries = db.query(WatchlistEntry).order_by(WatchlistEntry.symbol).all()
        db.expunge_all()
    reports = []
    for entry in entries:
        result, _ = service._calculate(entry, now)
        daily = service._daily[entry.symbol][1]
        benchmark = service._daily["SPY"][1]
        high, low, close = (
            np.array([float(getattr(bar, field)) for bar in daily]) for field in ("high", "low", "close")
        )
        indicators = daily_indicators(daily)
        expected = {
            "ema20": talib.EMA(close, 20)[-1],
            "sma50": talib.SMA(close, 50)[-1],
            "rsi14": talib.RSI(close, 14)[-1],
            "atr14": talib.ATR(high, low, close, 14)[-1],
            "adx14": talib.ADX(high, low, close, 14)[-1],
            "plus_di": talib.PLUS_DI(high, low, close, 14)[-1],
            "minus_di": talib.MINUS_DI(high, low, close, 14)[-1],
        }
        actual = {metric.id: metric.value for metric in result.metrics}
        actual.update(plus_di=float(indicators.plus_di), minus_di=float(indicators.minus_di))
        benchmark_by_day = {bar.starts_at.astimezone(NEW_YORK).date(): bar.close for bar in benchmark}
        dates = [bar.starts_at.astimezone(NEW_YORK).date() for bar in daily]
        for length in (5, 20):
            expected[f"rs{length}"] = 100 * (
                float(daily[-1].close) / float(daily[-length-1].close)
                - float(benchmark_by_day[dates[-1]]) / float(benchmark_by_day[dates[-length-1]])
            )
        window = analysis_window(service._calendar, now)
        prior = [bar for bar in daily if bar.starts_at.astimezone(NEW_YORK).date() < window.context_date][-20:]
        expected["range_high"] = float(max(bar.high for bar in prior))
        expected["range_low"] = float(min(bar.low for bar in prior))
        if window.daily_date == window.context_date:
            expected["extension"] = (close[-1] - expected["ema20"]) / expected["atr14"]
        # Independently sum complete regular-session grids at the same elapsed time.
        intraday = service._intraday.get(entry.symbol)
        if intraday:
            volumes = {bar.starts_at: bar.volume for bar in intraday[2]}
            session = service._calendar[window.context_date]
            elapsed = window.context_through - session.opens_at
            comparable = [
                value for day, value in sorted(service._calendar.items())
                if day <= window.context_date and value.closes_at - value.opens_at >= elapsed
            ][-21:]
            from datetime import timedelta
            totals = [
                sum(volumes[session.opens_at + timedelta(minutes=5*i)]
                    for i in range(int(elapsed.total_seconds()) // 300))
                for session in comparable
            ]
            expected["rvol20"] = totals[-1] / (sum(totals[:-1]) / 20)
        differences = {}
        for key, reference in expected.items():
            observed = actual[key]
            assert observed is not None and math.isfinite(reference), (entry.symbol, key, "missing")
            differences[key] = abs(observed - reference)
            assert math.isclose(observed, reference, abs_tol=1e-8, rel_tol=1e-10), (entry.symbol, key)
        report = {
            "symbol": entry.symbol,
            "sessions": len(daily),
            "readings_checked": len(differences),
            "max_absolute_difference": max(differences.values()),
            "conditions": {row.id: row.condition for row in result.metrics},
        }
        reports.append(report)
        print(json.dumps(report), flush=True)
    payload = {"at": now.isoformat(), "reference": f"TA-Lib {talib.__version__}", "stocks": reports}
    (Path(__file__).parent / "live-results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"PASS: {len(reports)} stocks checked, no server or stream started.", flush=True)


if __name__ == "__main__":
    main()
