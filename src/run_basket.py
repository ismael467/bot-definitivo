"""Bot de cesta (paper trading): ETH, ZEC y XRP, una posicion a la vez con todo el capital.
Independiente del bot de ETH: usa sus propios archivos data/basket_*."""
import csv
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

import basket_engine  # noqa: E402
from run_bot import build_signal_dataframe  # noqa: E402
from state_store import load_state, save_state  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config_basket.json")
STATE_PATH = os.path.join(ROOT, "data", "basket_state.json")
TRADES_PATH = os.path.join(ROOT, "data", "basket_trades_log.csv")
METRICS_PATH = os.path.join(ROOT, "data", "basket_metrics.json")
HEADER = ["coin", "side", "entry_time", "exit_time", "entry_price", "exit_price",
          "return_pct", "pnl_usd", "equity_after"]


def append_trades(trades, already):
    new = trades[already:]
    if not new:
        return
    exists = os.path.exists(TRADES_PATH)
    with open(TRADES_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if not exists:
            w.writeheader()
        w.writerows(new)


def write_metrics(state, cfg):
    with open(METRICS_PATH, "w") as f:
        json.dump(basket_engine.compute_metrics(state, cfg["starting_capital"]), f, indent=2)


def main():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Bot cesta: {', '.join(cfg['symbols'])}")
    dfs = {c: build_signal_dataframe(c, cfg) for c in cfg["symbols"]}
    state = load_state(STATE_PATH, cfg["starting_capital"])
    before = len(state["trades"])

    if state.get("last_processed_candle_ms") is None:      # arranque limpio
        state["last_processed_candle_ms"] = min(int(df["t"].iloc[-1]) for df in dfs.values())
        save_state(STATE_PATH, state)
        write_metrics(state, cfg)
        print("Primera ejecucion: cesta inicializada. Las operaciones empezaran con las velas siguientes.")
        return

    state, events = basket_engine.process_new_candles(dfs, state, cfg)
    for e in events:
        print(" -", e)
    append_trades(state["trades"], before)
    save_state(STATE_PATH, state)
    write_metrics(state, cfg)
    print("Metricas:", json.dumps(basket_engine.compute_metrics(state, cfg["starting_capital"]), indent=2))


if __name__ == "__main__":
    main()
