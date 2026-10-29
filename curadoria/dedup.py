"""Deduplicação: DOI → título exato → título fuzzy no mesmo ano.

Duplicatas são marcadas (is_canonical=False, dup_of=<chave canônica>), nunca apagadas.
"""
import pandas as pd
from rapidfuzz import fuzz, process

import config
from .keys import normalize_title


class _UF:
    def __init__(self, n):
        self.p = list(range(n))
        self.metodo = {}

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b, metodo):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)
            self.metodo.setdefault(max(a, b), metodo)


def dedup(df: pd.DataFrame, limiar: int = config.DEDUP_FUZZY_LIMIAR) -> pd.DataFrame:
    df = df.reset_index(drop=True).copy()
    n = len(df)
    uf = _UF(n)
    tnorm = df["title"].map(normalize_title)

    for coluna, metodo in [(df["doi"].fillna(""), "doi"), (tnorm, "titulo_exato")]:
        primeiro = {}
        for i, v in enumerate(coluna):
            if not v:
                continue
            if v in primeiro:
                uf.union(primeiro[v], i, metodo)
            else:
                primeiro[v] = i

    anos = df["year"].fillna(-1).astype(int)
    for ano in anos.unique():
        idx = [i for i in range(n) if anos[i] == ano and tnorm[i]]
        if len(idx) < 2:
            continue
        m = process.cdist([tnorm[i] for i in idx], [tnorm[i] for i in idx],
                          scorer=fuzz.token_sort_ratio, score_cutoff=limiar)
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                if m[a][b]:
                    uf.union(idx[a], idx[b], "titulo_fuzzy")

    grupos = {}
    for i in range(n):
        grupos.setdefault(uf.find(i), []).append(i)

    def completude(i):
        tem_doi = bool(df.at[i, "doi"])
        return (tem_doi, len(str(df.at[i, "abstract"] or "")), -i)

    df["is_canonical"] = False
    df["dup_of"] = ""
    df["dup_method"] = ""
    df["dup_group_size"] = 1
    for membros in grupos.values():
        canon = max(membros, key=completude)
        df.at[canon, "is_canonical"] = True
        for i in membros:
            df.at[i, "dup_group_size"] = len(membros)
            if i != canon:
                df.at[i, "dup_of"] = df.at[canon, "paper_key"]
                df.at[i, "dup_method"] = uf.metodo.get(i, "") or next(
                    (uf.metodo[j] for j in membros if j in uf.metodo), "")
    return df
