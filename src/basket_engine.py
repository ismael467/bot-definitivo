"""Cesta de mercados: UNA posicion a la vez con todo el capital.

Reglas (fijadas de antemano, no se tocan segun resultados):
 - Misma senal que el bot de ETH (RSI 1h + filtro SMA200 4h + trailing stop 4%).
 - Se miran las velas de todos los mercados en orden cronologico.
 - Con posicion abierta: solo se gestiona su trailing stop. Las senales de los otros mercados se ignoran.
 - Sin posicion: si en la misma hora saltan senales en varios mercados, se elige el primero de la
   lista "symbols" (prioridad = orden en que salieron en el screener del 2026-10-20).
 - Maximo 2 entradas al dia (UTC) en total.
"""
from datetime import datetime, timezone


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _day(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _close(state, cfg, exit_price, exit_ms, events):
    pos = state["position"]
    gross = exit_price / pos["entry_price"] - 1 if pos["side"] == "long" else pos["entry_price"] / exit_price - 1
    net = gross - 2 * cfg["fee_pct"]
    pnl = state["equity"] * net
    state["equity"] += pnl
    tr = {"coin": pos["coin"], "side": pos["side"], "entry_time": _iso(pos["entry_ms"]),
          "exit_time": _iso(exit_ms), "entry_price": round(pos["entry_price"], 6),
          "exit_price": round(exit_price, 6), "return_pct": round(net * 100, 4),
          "pnl_usd": round(pnl, 4), "equity_after": round(state["equity"], 4)}
    state["trades"].append(tr)
    state["position"] = None
    events.append(f"CIERRE {tr['coin']} {tr['side']} {tr['entry_price']} -> {tr['exit_price']} ({tr['return_pct']}%)")


def process_new_candles(dfs, state, cfg):
    """dfs: {coin: dataframe con t, OPEN, HIGH, LOW, CLOSE, RSI, PREV_RSI, SMA200_4H}."""
    events = []
    last = state["last_processed_candle_ms"]
    rows = {}
    for coin, df in dfs.items():
        for r in df.itertuples(index=False):
            t = int(r.t)
            if last is None or t > last:
                rows.setdefault(t, {})[coin] = r
    trail = cfg["trail_pct"]
    for t in sorted(rows):
        by_coin = rows[t]
        pos = state["position"]
        if pos is not None and pos["coin"] in by_coin:
            r = by_coin[pos["coin"]]
            if pos["side"] == "long":
                stop = pos["extreme"] * (1 - trail)
                if r.LOW <= stop:
                    _close(state, cfg, min(stop, r.OPEN), t, events)
                else:
                    pos["extreme"] = max(pos["extreme"], r.HIGH)
            else:
                stop = pos["extreme"] * (1 + trail)
                if r.HIGH >= stop:
                    _close(state, cfg, max(stop, r.OPEN), t, events)
                else:
                    pos["extreme"] = min(pos["extreme"], r.LOW)
        if state["position"] is None:
            day = _day(t)
            td = state["trades_today"]
            if td["date"] != day:
                td["date"], td["count"] = day, 0
            if td["count"] < cfg["max_trades_per_day"]:
                for coin in cfg["symbols"]:          # el orden de la lista es la prioridad
                    r = by_coin.get(coin)
                    if r is None or r.RSI != r.RSI or r.PREV_RSI != r.PREV_RSI or r.SMA200_4H != r.SMA200_4H:
                        continue
                    side = None
                    if r.PREV_RSI <= cfg["oversold"] < r.RSI and r.CLOSE > r.SMA200_4H:
                        side = "long"
                    elif r.PREV_RSI >= cfg["overbought"] > r.RSI and r.CLOSE < r.SMA200_4H:
                        side = "short"
                    if side:
                        state["position"] = {"coin": coin, "side": side, "entry_price": float(r.CLOSE),
                                             "entry_ms": t, "extreme": float(r.CLOSE)}
                        td["count"] += 1
                        events.append(f"ENTRADA {coin} {side} a {r.CLOSE}")
                        break
        last = t
    state["last_processed_candle_ms"] = last
    return state, events


def compute_metrics(state, starting_capital):
    trades = state.get("trades", [])
    n = len(trades)
    rets = [t["return_pct"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    peak, mdd = starting_capital, 0.0
    for t in trades:
        peak = max(peak, t["equity_after"])
        mdd = max(mdd, (peak - t["equity_after"]) / peak * 100)
    by = {}
    for t in trades:
        b = by.setdefault(t["coin"], {"trades": 0, "sum_return_pct": 0.0})
        b["trades"] += 1
        b["sum_return_pct"] = round(b["sum_return_pct"] + t["return_pct"], 2)
    return {
        "equity": round(state["equity"], 2),
        "total_return_pct": round((state["equity"] / starting_capital - 1) * 100, 2),
        "closed_trades": n,
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else None,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
        "max_drawdown_pct": round(mdd, 2),
        "by_coin": by,
        "open_position": state["position"],
    }
