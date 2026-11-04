"""Punto de entrada: se ejecuta 1 vez/hora en GitHub Actions. 100% paper trading (sin claves)."""
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd  # noqa: E402
from hyperliquid_client import get_candles, get_mid_price  # noqa: E402
from indicators import rsi_wilder, sma  # noqa: E402
from state_store import load_state, save_state  # noqa: E402
import engine  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "data", "state.json")
TRADES_LOG_PATH = os.path.join(ROOT, "data", "trades_log.csv")
METRICS_PATH = os.path.join(ROOT, "data", "metrics.json")
HEADER = ["side", "entry_time", "exit_time", "entry_price", "exit_price",
          "return_pct", "pnl_usd", "equity_after"]


def candles_to_df(raw):
    if not raw:
        return pd.DataFrame(columns=["T", "OPEN", "HIGH", "LOW", "CLOSE"])
    df = pd.DataFrame(raw).rename(columns={"o": "OPEN", "h": "HIGH", "l": "LOW", "c": "CLOSE"})
    for c in ["OPEN", "HIGH", "LOW", "CLOSE"]:
        df[c] = df[c].astype(float)
    df["T"] = df["T"].astype("int64")
    return df[["T", "OPEN", "HIGH", "LOW", "CLOSE"]].sort_values("T").drop_duplicates("T").reset_index(drop=True)


def build_signal_dataframe(coin, cfg, now_ms=None):
    now_ms = now_ms or int(time.time() * 1000)
    day = 24 * 3600 * 1000
    df1h = candles_to_df(get_candles(coin, cfg["signal_interval"], now_ms - 45 * day, now_ms))
    df4h = candles_to_df(get_candles(coin, cfg["trend_interval"], now_ms - 120 * day, now_ms))
    df1h = df1h[df1h["T"] <= now_ms].reset_index(drop=True)   # solo velas ya cerradas
    df4h = df4h[df4h["T"] <= now_ms].reset_index(drop=True)
    if len(df1h) < cfg["rsi_period"] + 2:
        raise RuntimeError("Pocas velas 1h devueltas para calcular RSI.")
    drift_h = abs(now_ms - int(df1h["T"].iloc[-1])) / 3_600_000
    if drift_h > 6:
        raise RuntimeError(f"Ultima vela 1h a {drift_h:.1f}h de 'ahora': datos obsoletos o unidades raras. Abortando.")
    df1h["RSI"] = rsi_wilder(df1h["CLOSE"], cfg["rsi_period"])
    df1h["PREV_RSI"] = df1h["RSI"].shift(1)
    df4h["SMA200"] = sma(df4h["CLOSE"], cfg["trend_sma_period"]).shift(1)  # sin lookahead
    s = df4h.dropna(subset=["SMA200"])[["T", "SMA200"]]
    m = pd.merge_asof(df1h.sort_values("T"), s.sort_values("T"), on="T", direction="backward")
    m = m.rename(columns={"SMA200": "SMA200_4H", "T": "t"})
    return m[["t", "OPEN", "HIGH", "LOW", "CLOSE", "RSI", "PREV_RSI", "SMA200_4H"]]


def append_trades(trades, already):
    new = trades[already:]
    if not new:
        return
    exists = os.path.exists(TRADES_LOG_PATH)
    with open(TRADES_LOG_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if not exists:
            w.writeheader()
        w.writerows(new)


def write_metrics(state, cfg):
    with open(METRICS_PATH, "w") as f:
        json.dump(engine.compute_metrics(state, cfg["starting_capital"]), f, indent=2)


def main():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    coin = cfg["symbol"]
    print(f"[{datetime.now(timezone.utc).isoformat()}] Bot RSI para {coin}")
    df = build_signal_dataframe(coin, cfg)
    state = load_state(STATE_PATH, cfg["starting_capital"])
    before = len(state["trades"])

    if state.get("last_processed_candle_ms") is None:   # arranque limpio
        state["last_processed_candle_ms"] = int(df["t"].iloc[-1])
        save_state(STATE_PATH, state)
        write_metrics(state, cfg)
        print(f"Primera ejecucion: paper trading inicializado para {coin}. "
              "Las operaciones empezaran con las velas siguientes.")
        return

    state, events = engine.process_new_candles(df, state, cfg)
    for e in events:
        print(" -", e)
    append_trades(state["trades"], before)
    save_state(STATE_PATH, state)
    write_metrics(state, cfg)
    try:
        print(f"Precio actual {coin}: {get_mid_price(coin)}")
    except Exception as e:  # noqa: BLE001
        print(f"(sin precio actual: {e})")
    print("Metricas:", json.dumps(engine.compute_metrics(state, cfg["starting_capital"]), indent=2))


if __name__ == "__main__":
    main()
