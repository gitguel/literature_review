"""Snowball para trás: referências dos selecionados, ordenadas por co-citação.

Os mais co-citados pelos artigos recentes costumam ser justamente os fundacionais.
"""
from datetime import datetime

import pandas as pd

import config
from . import decisions
from .bibio import append_entries, to_entry
from .keys import paper_key, title_year_key
from .openalex import OpenAlexClient
from .pipeline import chaves_no_corpus, load_view, run
from .projeto import Projeto
from .scoring import is_survey

COLUNAS = ["openalex_id", "cocitacao", "citado_por", "title", "year", "venue", "authors",
           "citations", "doi", "oa_type", "entry_type", "abstract", "keywords", "issn", "url"]


def run_snowball(proj: Projeto, incluir_talvez=False, progresso=None) -> pd.DataFrame:
    progresso = progresso or (lambda m: None)
    view = load_view(proj)
    cestas = config.CESTAS + (["talvez"] if incluir_talvez else [])
    sel = view[view["cesta"].isin(cestas)]
    contagem = {}
    for titulo, refs in zip(sel["title"], sel["referenced_works"]):
        for w in set(str(refs or "").split("|")) - {""}:
            contagem.setdefault(w, []).append(titulo)
    ranking = sorted(contagem.items(), key=lambda kv: -len(kv[1]))
    ranking = [kv for kv in ranking if len(kv[1]) >= config.SNOWBALL_MIN_COCITACAO]
    ranking = ranking[:config.SNOWBALL_MAX_CANDIDATOS]
    progresso(f"{len(sel)} selecionados citam {len(contagem)} obras; buscando as {len(ranking)} mais co-citadas")
    cli = OpenAlexClient(proj.dir / "cache", progresso=progresso)
    metas = cli.works_by_ids([w for w, _ in ranking])
    linhas = []
    for w, citantes in ranking:
        m = metas.get(w)
        if not m:
            continue
        linhas.append({**{k: m.get(k, "") for k in COLUNAS}, "openalex_id": w,
                       "cocitacao": len(citantes), "citado_por": " || ".join(citantes)})
    df = pd.DataFrame(linhas, columns=COLUNAS)
    df.to_csv(proj.derived("snowball.csv"), index=False)
    proj.derived("snowball_meta.txt").write_text(
        f"{datetime.now().isoformat(timespec='seconds')}|{len(sel)}|{cli.custo_usd:.4f}")
    progresso("Pronto")
    return df


def load_candidatos(proj: Projeto) -> pd.DataFrame:
    p = proj.derived("snowball.csv")
    if not p.exists():
        return pd.DataFrame(columns=COLUNAS + ["no_corpus", "paper_key", "sugestao", "decisao"])
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    df["cocitacao"] = pd.to_numeric(df["cocitacao"])
    df["citations"] = pd.to_numeric(df["citations"], errors="coerce").fillna(0).astype(int)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    view = load_view(proj, todos=True)
    idx = chaves_no_corpus(view) if len(view) else {}
    df["no_corpus"] = [idx.get(w) or idx.get(d) or idx.get(title_year_key(t, y)) or ""
                       for w, d, t, y in zip(df["openalex_id"], df["doi"], df["title"], df["year"])]
    df["paper_key"] = [nc or paper_key(d, t, y) for nc, d, t, y in
                       zip(df["no_corpus"], df["doi"], df["title"], df["year"])]
    cfg = proj.cfg
    idade = proj.ano_ref - df["year"]
    df["sugestao"] = ["grande_area" if is_survey(t, o) else "recente" if i <= int(cfg["anos_recente"])
                      else "fundacional" for t, o, i in zip(df["title"], df["oa_type"], idade.fillna(99))]
    cesta = decisions.latest(proj.dir, "cesta")
    df["decisao"] = df["paper_key"].map(lambda k: cesta.get(k, {}).get("value", ""))
    return df.sort_values(["cocitacao", "citations"], ascending=False)


def aceitar(proj: Projeto, openalex_id: str, cesta: str):
    """Aceita um candidato numa cesta. Se ainda não está no corpus, vai para snowball.bib."""
    df = load_candidatos(proj)
    linha = df[df["openalex_id"] == openalex_id]
    if linha.empty:
        raise KeyError(openalex_id)
    r = linha.iloc[0].to_dict()
    if not r["no_corpus"]:
        append_entries(proj.snowball_bib, [to_entry(r)])
        run(proj, online=False)   # rápido: tudo vem do cache
    decisions.append(proj.dir, "cesta", r["paper_key"], cesta, "snowball")
