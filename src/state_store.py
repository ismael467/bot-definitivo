import json
import os


def load_state(path: str, starting_capital: float) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"position": None, "equity": starting_capital, "trades": [],
            "trades_today": {"date": None, "count": 0}, "last_processed_candle_ms": None}


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
