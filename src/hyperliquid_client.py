"""Cliente de solo lectura para la Info API publica de Hyperliquid (sin claves)."""
import time
import requests

URL = "https://api.hyperliquid.xyz/info"


def _post(payload: dict, retries: int = 4):
    last = None
    for i in range(retries):
        try:
            r = requests.post(URL, json=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"Hyperliquid no responde: {last}")


def get_candles(coin: str, interval: str, start_ms: int, end_ms: int) -> list:
    return _post({"type": "candleSnapshot",
                  "req": {"coin": coin, "interval": interval,
                          "startTime": start_ms, "endTime": end_ms}})


def get_mid_price(coin: str) -> float:
    return float(_post({"type": "allMids"})[coin])
