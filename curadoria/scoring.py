"""Scores por cesta e cesta sugerida. Cada termo é normalizado em 0..1 no corpus."""
import re

import numpy as np
import pandas as pd

import config

_SURVEY_RE = re.compile("|".join(re.escape(p) for p in config.PALAVRAS_SURVEY), re.I)


def is_survey(title, oa_type="") -> bool:
    return oa_type in config.TIPOS_SURVEY_OPENALEX or bool(_SURVEY_RE.search(str(title or "")))


def _norm_log(s: pd.Series) -> pd.Series:
    v = np.log1p(s.fillna(0).clip(lower=0).astype(float))
    m = v.max()
    return v / m if m and m > 0 else v * 0


def score(df: pd.DataFrame, ano_ref: int, anos_recente: int, idade_min_fund: int) -> pd.DataFrame:
    """Espera as colunas year, citations, cocitacao, venue_rank_final, title, oa_type."""
    df = df.copy()
    ano = pd.to_numeric(df["year"], errors="coerce")
    df["idade"] = (ano_ref - ano).clip(lower=0)
    df["cit_ano"] = (df["citations"].fillna(0) / df["idade"].fillna(0).clip(lower=1)).round(1)
    df["is_survey"] = [is_survey(t, o) for t, o in zip(df["title"], df["oa_type"].fillna(""))]

    n_cit = _norm_log(df["citations"])
    n_cit_ano = _norm_log(df["cit_ano"])
    n_cocit = _norm_log(df["cocitacao"])
    bonus = df["venue_rank_final"].fillna("").map(lambda r: config.BONUS_VENUE.get(r, 0.0))

    eleg_ga = df["is_survey"]
    eleg_fund = (df["idade"] >= idade_min_fund) & ~df["is_survey"]
    eleg_rec = (df["idade"] <= anos_recente) & ~df["is_survey"]

    df["score_grande_area"] = np.where(eleg_ga, config.PESO_GA_CITACOES * n_cit, np.nan)
    df["score_fundacional"] = np.where(
        eleg_fund, config.PESO_FUND_CITACOES * n_cit + config.PESO_FUND_COCITACAO * n_cocit, np.nan)
    df["score_recente"] = np.where(
        eleg_rec, config.PESO_REC_CIT_ANO * n_cit_ano + config.PESO_REC_VENUE * bonus, np.nan)

    cols = [f"score_{c}" for c in config.CESTAS]
    df[cols] = df[cols].round(3)
    tem = df[cols].notna().any(axis=1)
    df["cesta_sugerida"] = ""
    df.loc[tem, "cesta_sugerida"] = df.loc[tem, cols].idxmax(axis=1).str.replace("score_", "", regex=False)
    df["score"] = df[cols].max(axis=1).fillna(0)
    return df
