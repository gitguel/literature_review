"""Orquestração: ler .bib → dedup → enriquecer (OpenAlex) → rankear → salvar derived/.

`run` gera o que é regenerável (derived/corpus.csv); `load_view` junta, a cada
leitura, o corpus com os logs de decisão, a co-citação e os scores.
"""
import json
from datetime import datetime

import pandas as pd

import config
from . import decisions
from .bibio import CAMPOS, read_bib
from .dedup import dedup
from .keys import normalize_title, title_year_key
from .openalex import OpenAlexClient, issns_of
from .projeto import Projeto
from .ranking import Ranker, best_rank
from .scoring import score

COLS_ENRIQ = ["citations", "oa_type", "venue_type", "referenced_works"]


def _origem(source: str) -> str:
    if source.startswith("openalex_"):
        return "busca"
    if source == "snowball":
        return "snowball"
    return "bib"


def _carregar_registros(proj: Projeto) -> pd.DataFrame:
    regs = []
    for p in proj.bibs():
        regs += read_bib(p)
    df = pd.DataFrame(regs, columns=CAMPOS)
    df["origem"] = df["source"].map(_origem)
    return df


def _lookup_path(proj):
    return proj.dir / "cache" / "lookup.json"


def enriquecer(proj: Projeto, df: pd.DataFrame, online=True, progresso=None) -> pd.DataFrame:
    """Casa cada registro canônico com uma obra do OpenAlex e completa os campos vazios.

    lookup.json guarda paper_key → id OpenAlex ("" = não encontrado) para não repetir buscas.
    """
    progresso = progresso or (lambda m: None)
    cli = OpenAlexClient(proj.dir / "cache", progresso=progresso)
    lp = _lookup_path(proj)
    lookup = json.loads(lp.read_text()) if lp.exists() else {}

    for _, r in df[df["openalex_id"].astype(bool)].iterrows():
        lookup.setdefault(r["paper_key"], r["openalex_id"])

    alvo = df[df["is_canonical"]]
    if online:
        com_doi = alvo[(alvo["doi"] != "") & ~alvo["paper_key"].isin(lookup)]
        if len(com_doi):
            progresso(f"Enriquecendo {len(com_doi)} registros por DOI (em lote)")
            achados = cli.works_by_dois(com_doi["doi"].tolist())
            for _, r in com_doi.iterrows():
                lookup[r["paper_key"]] = achados[r["doi"]]["openalex_id"] if r["doi"] in achados else ""
        sem_doi = alvo[(alvo["doi"] == "") & ~alvo["paper_key"].isin(lookup)]
        for i, (_, r) in enumerate(sem_doi.iterrows(), 1):
            progresso(f"Buscando por título {i}/{len(sem_doi)}")
            m = cli.work_by_title(r["title"], r["year"])
            lookup[r["paper_key"]] = m["openalex_id"] if m else ""
            if i % 20 == 0:
                lp.write_text(json.dumps(lookup))
        lp.write_text(json.dumps(lookup))

    ids = [w for w in (lookup.get(k, "") for k in alvo["paper_key"]) if w]
    metas = cli.works_by_ids(ids) if online else {w: m for w in ids if (m := cli.cached(w))}

    df = df.copy()
    for c in COLS_ENRIQ:
        df[c] = None
    for i, r in df.iterrows():
        if not r["is_canonical"]:
            continue
        m = metas.get(lookup.get(r["paper_key"], ""))
        if not m:
            continue
        df.at[i, "openalex_id"] = m["openalex_id"]
        df.at[i, "citations"] = m["citations"]
        df.at[i, "oa_type"] = m["oa_type"]
        df.at[i, "venue_type"] = m["venue_type"]
        df.at[i, "referenced_works"] = "|".join(m["referenced_works"])
        for campo in ["abstract", "venue", "issn", "keywords", "authors", "url"]:
            if not r[campo] and m.get(campo):
                df.at[i, campo] = m[campo]
        if r["entry_type"] == "misc" and m["entry_type"] != "misc":
            df.at[i, "entry_type"] = m["entry_type"]
    progresso(f"OpenAlex: {cli.requisicoes} requisições, custo ~US$ {cli.custo_usd:.4f}")
    return df


def rankear(proj: Projeto, df: pd.DataFrame) -> pd.DataFrame:
    rk = Ranker.from_project(proj.dir)
    df = df.copy()
    novas = []
    for _, r in df.iterrows():
        res = {}
        if r["entry_type"] == "article" or r.get("venue_type") == "journal":
            res.update(rk.match_sjr(r["venue"], issns_of(r)))
        else:
            res.update(rk.match_core(r["venue"]))
        novas.append(res)
    extra = pd.DataFrame(novas, index=df.index,
                         columns=["core_rank", "core_match", "core_method", "core_score",
                                  "sjr_quartil", "sjr_match", "sjr_method", "sjr_score"])
    extra = extra.astype(object).fillna("")
    return pd.concat([df, extra], axis=1)


def propostas_recuperacao(df: pd.DataFrame) -> pd.DataFrame:
    """Canônica sem rank, mas com duplicata rankeada → proposta (nunca aplicada sozinha)."""
    df = df.assign(rank_pipeline=[best_rank(c, s) for c, s in
                                  zip(df["core_rank"], df["sjr_quartil"])])
    canon = df[df["is_canonical"] & (df["rank_pipeline"] == "")]
    dups = df[~df["is_canonical"] & (df["rank_pipeline"] != "")]
    props = []
    for _, d in dups.iterrows():
        c = canon[canon["paper_key"] == d["dup_of"]]
        if len(c):
            c = c.iloc[0]
            props.append({"key": c["paper_key"], "title": c["title"], "abstract": c["abstract"],
                          "venue_canonica": c["venue"], "venue_duplicata": d["venue"],
                          "rank_proposto": d["rank_pipeline"]})
    return pd.DataFrame(props, columns=["key", "title", "abstract", "venue_canonica",
                                        "venue_duplicata", "rank_proposto"]).drop_duplicates("key")


def run(proj: Projeto, online=None, progresso=None) -> dict:
    progresso = progresso or (lambda m: None)
    online = proj.cfg.get("enriquecer", True) if online is None else online
    progresso("Lendo arquivos .bib")
    df = _carregar_registros(proj)
    if df.empty:
        for nome in ["corpus.csv", "rank_recovery.csv", "contagens.json"]:
            proj.derived(nome).unlink(missing_ok=True)
        return {"coletados": 0, "unicos": 0}
    progresso(f"Deduplicando {len(df)} registros")
    df = dedup(df)
    df = enriquecer(proj, df, online=online, progresso=progresso)
    progresso("Rankeando venues")
    df = rankear(proj, df)
    df.to_csv(proj.derived("corpus.csv"), index=False)
    propostas_recuperacao(df).to_csv(proj.derived("rank_recovery.csv"), index=False)
    cont = {
        "coletados": int(len(df)),
        "unicos": int(df["is_canonical"].sum()),
        "por_fonte": df.groupby("source").size().to_dict(),
        "enriquecidos": int(df.loc[df["is_canonical"], "citations"].notna().sum()),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
    }
    proj.derived("contagens.json").write_text(json.dumps(cont, ensure_ascii=False, indent=2))
    progresso("Pronto")
    return cont


# --- visão com decisões ---------------------------------------------------------
def _ler_corpus(proj: Projeto) -> pd.DataFrame:
    p = proj.derived("corpus.csv")
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, dtype={"paper_key": str, "doi": str, "openalex_id": str, "issn": str,
                               "referenced_works": str, "core_rank": str, "sjr_quartil": str},
                     keep_default_na=False, na_values={"citations": [""], "year": [""]})
    df["is_canonical"] = df["is_canonical"].astype(str) == "True"
    return df


def load_view(proj: Projeto, todos=False) -> pd.DataFrame:
    """Corpus canônico + decisões + co-citação + scores. Nunca descarta linhas canônicas."""
    df = _ler_corpus(proj)
    if df.empty:
        return df
    if not todos:
        df = df[df["is_canonical"]].copy()
    d = proj.dir

    venue_manual = decisions.latest(d, "venue_rank")
    recup = decisions.latest(d, "rank_recovery")
    df["rank_pipeline"] = [best_rank(c, s) for c, s in zip(df["core_rank"], df["sjr_quartil"])]
    df["rank_manual"] = df["venue"].map(lambda v: venue_manual.get(normalize_title(v), {}).get("value", ""))
    df["rank_recuperado"] = df["paper_key"].map(
        lambda k: recup[k]["value"] if k in recup and recup[k]["value"] != "rejeitado" else "")
    df["venue_rank_final"] = [m or r or p for m, r, p in
                              zip(df["rank_manual"], df["rank_recuperado"], df["rank_pipeline"])]
    df.loc[df["venue_rank_final"] == "sem_rank", "venue_rank_final"] = ""

    cesta = decisions.latest(d, "cesta")
    df["cesta"] = df["paper_key"].map(lambda k: cesta.get(k, {}).get("value", "pendente") or "pendente")
    df["motivo"] = df["paper_key"].map(lambda k: cesta.get(k, {}).get("note", ""))
    df["decidido_em"] = df["paper_key"].map(lambda k: cesta.get(k, {}).get("timestamp", ""))
    ordem = decisions.latest(d, "ordem")
    df["ordem"] = df["paper_key"].map(lambda k: float(ordem[k]["value"]) if k in ordem else float("nan"))
    lido = decisions.latest(d, "lido")
    df["lido"] = df["paper_key"].map(lambda k: lido.get(k, {}).get("value") == "1")

    # co-citação: quantos selecionados citam cada paper
    sel = df[df["cesta"].isin(config.CESTAS)]
    contagem = {}
    for k, refs in zip(sel["paper_key"], sel["referenced_works"]):
        for w in set(str(refs or "").split("|")) - {""}:
            contagem.setdefault(w, set()).add(k)
    df["cocitacao"] = [len(contagem.get(w, set()) - {k}) if w else 0
                       for w, k in zip(df["openalex_id"], df["paper_key"])]

    if "oa_type" not in df:
        df["oa_type"] = ""
    df["citations"] = pd.to_numeric(df["citations"], errors="coerce")
    cfg = proj.cfg
    return score(df, proj.ano_ref, int(cfg["anos_recente"]), int(cfg["idade_min_fundacional"]))


def chaves_no_corpus(df: pd.DataFrame) -> dict[str, str]:
    """Índice para casar candidatos externos com o corpus: id OpenAlex, DOI ou título|ano → paper_key."""
    idx = {}
    for _, r in df.iterrows():
        for k in (r.get("openalex_id"), r.get("doi"), title_year_key(r["title"], r["year"])):
            if k:
                idx.setdefault(str(k), r["dup_of"] or r["paper_key"])
    return idx
