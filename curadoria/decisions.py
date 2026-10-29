"""Logs de decisão humana: um CSV por tipo, append-only, a última linha vence."""
import csv
from datetime import datetime
from pathlib import Path

import pandas as pd

LOGS = ["cesta", "venue_rank", "rank_recovery", "ordem", "lido"]
COLUNAS = ["key", "value", "timestamp", "note"]


def _path(project_dir, log) -> Path:
    if log not in LOGS:
        raise ValueError(f"log desconhecido: {log}")
    return Path(project_dir) / "decisions" / f"{log}.csv"


def append(project_dir, log, key, value, note=""):
    p = _path(project_dir, log)
    p.parent.mkdir(parents=True, exist_ok=True)
    novo = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(COLUNAS)
        w.writerow([key, value, datetime.now().isoformat(timespec="seconds"), note or ""])


def history(project_dir, log) -> pd.DataFrame:
    p = _path(project_dir, log)
    if not p.exists():
        return pd.DataFrame(columns=COLUNAS)
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def latest(project_dir, log) -> dict[str, dict]:
    """{key: {"value", "timestamp", "note"}} com a última decisão de cada chave."""
    h = history(project_dir, log)
    return {r["key"]: {"value": r["value"], "timestamp": r["timestamp"], "note": r["note"]}
            for r in h.to_dict("records")}   # linhas posteriores sobrescrevem as anteriores
