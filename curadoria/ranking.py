"""Rank de venue opcional: CORE (conferências) e SCImago/SJR (periódicos).

CORE: sigla → nome exato → fuzzy só nas palavras distintivas. Workshops não herdam
o rank da conferência principal. SJR: só para @article, ISSN → nome exato → fuzzy.
"""
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

import config
from .keys import normalize_issn, normalize_title

RANKS_CORE = ["A*", "A", "B", "C"]
QUARTIS = ["Q1", "Q2", "Q3", "Q4"]


def distinctive(nome) -> str:
    t = normalize_title(nome)
    t = re.sub(r"\b\d+(st|nd|rd|th)?\b", " ", t)   # ordinais e anos
    return " ".join(w for w in t.split() if w not in config.PALAVRAS_GENERICAS_VENUE)


def _is_workshop(nome) -> bool:
    return bool(re.search(r"\bworkshops?\b", str(nome), re.I))


def _acronimos(venue) -> set[str]:
    """Siglas candidatas: entre parênteses ou palavras em caixa alta (ICML 2020, NeurIPS'21)."""
    s = str(venue)
    cands = set(re.findall(r"\(([A-Za-z][A-Za-z0-9\-&]{1,15})", s))
    cands |= {w for w in re.findall(r"\b[A-Z][A-Za-z]*[A-Z][A-Za-z]*\b", s) if len(w) >= 3}
    return {re.sub(r"['’]?\d+$", "", c).upper() for c in cands}


# --- carregamento das tabelas ------------------------------------------------
def load_core(path) -> pd.DataFrame:
    """Aceita o CSV do portal CORE (sem cabeçalho: id,título,sigla,fonte,rank,...) ou com cabeçalho."""
    df = pd.read_csv(path, header=None, dtype=str, keep_default_na=False, encoding_errors="replace")
    cab = [c.strip().lower() for c in df.iloc[0]]
    if "title" in cab and "rank" in cab:
        df.columns = cab
        df = df.iloc[1:]
    else:
        df = df.rename(columns={1: "title", 2: "acronym", 4: "rank"})
    df = df[["title", "acronym", "rank"]].copy()
    df["rank"] = df["rank"].str.strip()
    df = df[df["rank"].isin(RANKS_CORE)]
    df["acronym"] = df["acronym"].str.strip().str.upper()
    df["norm"] = df["title"].map(normalize_title)
    df["dist"] = df["title"].map(distinctive)
    df["workshop"] = df["title"].map(_is_workshop)
    return df.reset_index(drop=True)


def load_sjr(path) -> pd.DataFrame:
    """CSV exportado do scimagojr.com (separador ';', colunas Title, Issn, SJR Best Quartile)."""
    df = pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding_errors="replace")
    cols = {c.lower().strip(): c for c in df.columns}
    df = pd.DataFrame({
        "title": df[cols["title"]],
        "issn": df[cols["issn"]] if "issn" in cols else "",
        "quartil": df[cols["sjr best quartile"]].str.strip(),
    })
    df = df[df["quartil"].isin(QUARTIS)].copy()
    df["norm"] = df["title"].map(normalize_title)
    return df.reset_index(drop=True)


# --- matching -------------------------------------------------------------------
class Ranker:
    def __init__(self, core: pd.DataFrame | None = None, sjr: pd.DataFrame | None = None):
        self.core, self.sjr = core, sjr
        self._core_cache, self._sjr_cache = {}, {}
        if core is not None:
            self.core_por_sigla = {}
            for r in core.itertuples():
                if r.acronym:
                    self.core_por_sigla.setdefault(r.acronym, r)
            self.core_por_nome = {r.norm: r for r in core.itertuples()}
        if sjr is not None:
            self.sjr_por_issn = {}
            for r in sjr.itertuples():
                for i in str(r.issn).split(","):
                    i = normalize_issn(i)
                    if i:
                        self.sjr_por_issn.setdefault(i, r)
            self.sjr_por_nome = {r.norm: r for r in sjr.itertuples()}

    @classmethod
    def from_project(cls, project_dir):
        rk = Path(project_dir) / "rankings"
        core = load_core(rk / "core.csv") if (rk / "core.csv").exists() else None
        sjr = load_sjr(rk / "sjr.csv") if (rk / "sjr.csv").exists() else None
        return cls(core, sjr)

    def match_core(self, venue) -> dict:
        if self.core is None or not venue:
            return {}
        if venue in self._core_cache:
            return self._core_cache[venue]
        ws = _is_workshop(venue)
        res = {}
        norm = normalize_title(venue)
        if norm in self.core_por_nome:
            r = self.core_por_nome[norm]
            res = {"core_rank": r.rank, "core_match": r.title, "core_method": "nome_exato", "core_score": 100}
        if not res:
            for sig in _acronimos(venue):
                r = self.core_por_sigla.get(sig)
                if r is not None and r.workshop == ws:
                    res = {"core_rank": r.rank, "core_match": r.title, "core_method": "sigla", "core_score": 100}
                    break
        if not res:
            d = distinctive(venue)
            cands = self.core[self.core["workshop"] == ws]
            if d and len(cands):
                m = process.extractOne(d, cands["dist"].tolist(), scorer=fuzz.token_sort_ratio,
                                       score_cutoff=config.CORE_FUZZY_LIMIAR)
                if m:
                    r = cands.iloc[m[2]]
                    res = {"core_rank": r["rank"], "core_match": r["title"], "core_method": "fuzzy",
                           "core_score": round(m[1], 1)}
        self._core_cache[venue] = res
        return res

    def match_sjr(self, venue, issns: set[str]) -> dict:
        if self.sjr is None:
            return {}
        chave = (venue, tuple(sorted(issns)))
        if chave in self._sjr_cache:
            return self._sjr_cache[chave]
        res = {}
        for i in issns:
            r = self.sjr_por_issn.get(i)
            if r is not None:
                res = {"sjr_quartil": r.quartil, "sjr_match": r.title, "sjr_method": "issn", "sjr_score": 100}
                break
        norm = normalize_title(venue)
        if not res and norm in self.sjr_por_nome:
            r = self.sjr_por_nome[norm]
            res = {"sjr_quartil": r.quartil, "sjr_match": r.title, "sjr_method": "nome_exato", "sjr_score": 100}
        if not res and norm:
            m = process.extractOne(norm, self.sjr["norm"].tolist(), scorer=fuzz.ratio,
                                   score_cutoff=config.SJR_FUZZY_LIMIAR)
            if m:
                r = self.sjr.iloc[m[2]]
                res = {"sjr_quartil": r["quartil"], "sjr_match": r["title"], "sjr_method": "fuzzy",
                       "sjr_score": round(m[1], 1)}
        self._sjr_cache[chave] = res
        return res


def best_rank(core_rank, sjr_quartil) -> str:
    """O melhor rank disponível, para exibição e bônus."""
    vals = [v for v in (core_rank, sjr_quartil) if v]
    if not vals:
        return ""
    return max(vals, key=lambda v: config.BONUS_VENUE.get(v, 0))
