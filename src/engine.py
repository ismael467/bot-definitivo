"""Motor de decision (paper trading). Procesa velas 1h cerradas, de una en una, en orden.

Por cada vela nueva:
 1. Si hay posicion abierta: se evalua el trailing stop con el Low/High de la vela
    (el stop se calcula con el maximo/minimo de las velas ANTERIORES) y luego se actualiza el extremo.
 2. Si no hay posicion y no se ha llegado al maximo de entradas del dia (UTC), se mira la senal:
    largo: RSI cruza hacia arriba 30 y cierre > SMA200(4h); corto: RSI cruza hacia abajo 70 y cierre < SMA200(4h).
    La entrada es al cierre de la vela de la senal.
"""
from datetime import datetime, timezone


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _close_position(state, cfg, exit_price, exit_ms, events):
    pos = state["position"]
    if pos["side"] == "long":
        gross = exit_price / pos["entry_price"] - 1
    else:
        gross = pos["entry_price"] / exit_price - 1
    net = gross - 2 * cfg["fee_pct"]
    pnl = state["equity"] * net
    state["equity"] = state["equity"] + pnl
    trade = {"side": pos["side"], "entry_time": _iso(pos["entry_ms"]), "exit_time": _iso(exit_ms),
             "entry_price": round(pos["entry_price"], 4), "exit_price": round(exit_price, 4),
             "return_pct": round(net * 100, 4), "pnl_usd": round(pnl, 4),
             "equity_after": round(state["equity"], 4)}
    state["trades"].append(trade)
    state["position"] = None
    events.append(f"CIERRE {trade['side']} {trade['entry_price']} -> {trade['exit_price']} ({trade['return_pct']}%)")


def process_new_candles(df, state, cfg):
    events = []
    last = state["last_processed_candle_ms"]
    trail = cfg["trail_pct"]
    for row in df.itertuples(index=False):
        t = int(row.t)
        if last is not None and t <= last:
            continue
        pos = state["position"]
        if pos is not None:
            if pos["side"] == "long":
                stop = pos["extreme"] * (1 - trail)
                if row.LOW <= stop:
                    _close_position(state, cfg, min(stop, row.OPEN), t, events)
                else:
                    pos["extreme"] = max(pos["extreme"], row.HIGH)
            else:
                stop = pos["extreme"] * (1 + trail)
                if row.HIGH >= stop:
                    _close_position(state, cfg, max(stop, row.OPEN), t, events)
                else:
                    pos["extreme"] = min(pos["extreme"], row.LOW)
        if state["position"] is None and row.RSI == row.RSI and row.PREV_RSI == row.PREV_RSI \
                and row.SMA200_4H == row.SMA200_4H:
            day = _day(t)
            td = state["trades_today"]
            if td["date"] != day:
                td["date"], td["count"] = day, 0
            if td["count"] < cfg["max_trades_per_day"]:
                side = None
                if row.PREV_RSI <= cfg["oversold"] < row.RSI and row.CLOSE > row.SMA200_4H:
                    side = "long"
                elif row.PREV_RSI >= cfg["overbought"] > row.RSI and row.CLOSE < row.SMA200_4H:
                    side = "short"
                if side:
                    state["position"] = {"side": side, "entry_price": float(row.CLOSE),
                                         "entry_ms": t, "extreme": float(row.CLOSE)}
                    td["count"] += 1
                    events.append(f"ENTRADA {side} a {row.CLOSE}")
        last = t
    state["last_processed_candle_ms"] = last
    return state, events


def compute_metrics(state, starting_capital):
    trades = state.get("trades", [])
    n = len(trades)
    rets = [t["return_pct"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    peak, mdd, eq = starting_capital, 0.0, starting_capital
    for t in trades:
        eq = t["equity_after"]
        peak = max(peak, eq)
        mdd = max(mdd, (peak - eq) / peak * 100)

    def side(s):
        r = [t["return_pct"] for t in trades if t["side"] == s]
        return {"trades": len(r), "sum_return_pct": round(sum(r), 2)}

    return {
        "equity": round(state["equity"], 2),
        "total_return_pct": round((state["equity"] / starting_capital - 1) * 100, 2),
        "closed_trades": n,
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else None,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else None,
        "max_drawdown_pct": round(mdd, 2),
        "long": side("long"), "short": side("short"),
        "open_position": state["position"],
    }
