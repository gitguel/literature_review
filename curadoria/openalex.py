"""Cliente OpenAlex econômico: lotes por filtro, cache em disco por obra.

Custos (sem chave há um orçamento diário pequeno por IP): uma busca textual
custa ~10x uma consulta por filtro, então o enriquecimento usa lotes de DOIs/ids
e só cai na busca por título quando o registro não tem DOI.
"""
import json
import re
import time
from pathlib import Path

import requests
from rapidfuzz import fuzz

import config
from .keys import normalize_doi, normalize_title, normalize_issn

CAMPOS_SELECT = ("id,doi,display_name,publication_year,type,cited_by_count,primary_location,"
                 "authorships,abstract_inverted_index,referenced_works,keywords")


class OpenAlexErro(RuntimeError):
    pass


def short_id(oa_id) -> str:
    return str(oa_id or "").rstrip("/").split("/")[-1]


def reconstruct_abstract(inv) -> str:
    if not inv:
        return ""
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    return " ".join(w for _, w in sorted(pos))


def work_to_meta(w: dict) -> dict:
    """Converte uma obra do OpenAlex no formato de registro da plataforma."""
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    tipo_src = src.get("type") or ""
    tipo = w.get("type") or ""
    if tipo_src == "conference" or tipo == "conference-paper":
        entry_type = "inproceedings"
    elif tipo_src == "journal":
        entry_type = "article"
    elif tipo == "book-chapter":
        entry_type = "incollection"
    elif tipo == "book":
        entry_type = "book"
    else:
        entry_type = "misc"
    autores = [((a.get("author") or {}).get("display_name") or "") for a in w.get("authorships") or []]
    return {
        "openalex_id": short_id(w.get("id")),
        "doi": normalize_doi(w.get("doi") or ""),
        "title": w.get("display_name") or "",
        "year": w.get("publication_year"),
        "oa_type": tipo,
        "entry_type": entry_type,
        "venue": src.get("display_name") or "",
        "venue_type": tipo_src,
        "issn": ", ".join(src.get("issn") or []),
        "authors": " and ".join(a for a in autores if a),
        "citations": int(w.get("cited_by_count") or 0),
        "abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
        "keywords": "; ".join(k.get("display_name", "") for k in w.get("keywords") or []),
        "referenced_works": [short_id(r) for r in w.get("referenced_works") or []],
        "url": w.get("doi") or w.get("id") or "",
    }


class OpenAlexClient:
    def __init__(self, cache_dir, api_key=None, mailto=None, session=None, progresso=None):
        self.cache_dir = Path(cache_dir)
        self.works_dir = self.cache_dir / "works"
        self.works_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = config.OPENALEX_API_KEY if api_key is None else api_key
        self.mailto = config.OPENALEX_MAILTO if mailto is None else mailto
        self.session = session or requests.Session()
        self.progresso = progresso or (lambda msg: None)
        self.custo_usd = 0.0
        self.requisicoes = 0

    # --- HTTP ----------------------------------------------------------------
    def _get(self, path, params):
        params = dict(params)
        if self.api_key:
            params["api_key"] = self.api_key
        if self.mailto:
            params["mailto"] = self.mailto
        espera = 1.0
        for tentativa in range(config.OPENALEX_TENTATIVAS):
            try:
                r = self.session.get(f"{config.OPENALEX_URL}{path}", params=params,
                                     timeout=config.OPENALEX_TIMEOUT)
            except requests.RequestException as e:
                erro = str(e)
            else:
                self.requisicoes += 1
                if r.status_code == 200:
                    dados = r.json()
                    self.custo_usd += float((dados.get("meta") or {}).get("cost_usd") or 0)
                    return dados
                if r.status_code == 404:
                    return None
                erro = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            if tentativa < config.OPENALEX_TENTATIVAS - 1:
                time.sleep(espera)
                espera *= 2
        raise OpenAlexErro(f"Falha no OpenAlex ({path}): {erro}")

    # --- cache por obra --------------------------------------------------------
    def _cache_path(self, wid):
        return self.works_dir / f"{wid}.json"

    def cached(self, wid) -> dict | None:
        p = self._cache_path(wid)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def _store(self, work: dict) -> dict:
        meta = work_to_meta(work)
        self._cache_path(meta["openalex_id"]).write_text(json.dumps(meta, ensure_ascii=False),
                                                         encoding="utf-8")
        return meta

    # --- operações -------------------------------------------------------------
    def search(self, query, max_results=200, year_from=None, year_to=None) -> list[dict]:
        """Busca booleana em título+abstract. Ex.: '"federated learning" AND (contrastive OR "self-supervised")'."""
        filtros = [f"title_and_abstract.search:{query.replace(',', ' ')}"]
        if year_from:
            filtros.append(f"from_publication_date:{int(year_from)}-01-01")
        if year_to:
            filtros.append(f"to_publication_date:{int(year_to)}-12-31")
        metas, cursor = [], "*"
        while cursor and len(metas) < max_results:
            dados = self._get("/works", {"filter": ",".join(filtros), "select": CAMPOS_SELECT,
                                         "per-page": min(config.OPENALEX_POR_PAGINA, max_results),
                                         "cursor": cursor})
            if not dados:
                break
            for w in dados.get("results", []):
                metas.append(self._store(w))
            cursor = (dados.get("meta") or {}).get("next_cursor")
            if not dados.get("results"):
                break
            self.progresso(f"busca: {len(metas)} resultados")
        return metas[:max_results]

    def _lote(self, campo, valores) -> list[dict]:
        metas = []
        for i in range(0, len(valores), config.OPENALEX_LOTE):
            parte = valores[i:i + config.OPENALEX_LOTE]
            dados = self._get("/works", {"filter": f"{campo}:{'|'.join(parte)}",
                                         "select": CAMPOS_SELECT, "per-page": len(parte)})
            metas += [self._store(w) for w in (dados or {}).get("results", [])]
            self.progresso(f"{campo}: {min(i + len(parte), len(valores))}/{len(valores)}")
        return metas

    def works_by_ids(self, ids) -> dict[str, dict]:
        """Metadados por id OpenAlex (W...), usando o cache quando possível."""
        out, faltam = {}, []
        for wid in dict.fromkeys(short_id(i) for i in ids if i):
            m = self.cached(wid)
            if m:
                out[wid] = m
            else:
                faltam.append(wid)
        for m in self._lote("openalex_id", faltam):
            out[m["openalex_id"]] = m
        return out

    def works_by_dois(self, dois) -> dict[str, dict]:
        dois = list(dict.fromkeys(d for d in (normalize_doi(x) for x in dois) if d))
        return {m["doi"]: m for m in self._lote("doi", dois) if m["doi"]}

    def work_by_title(self, title, year=None) -> dict | None:
        q = re.sub(r"[^\w\s-]", " ", title)
        q = re.sub(r"\b(AND|OR|NOT)\b", lambda m: m.group(0).lower(), q)
        dados = self._get("/works", {"filter": f"title.search:{q}", "select": CAMPOS_SELECT,
                                     "per-page": 5})
        alvo = normalize_title(title)
        melhor, melhor_score = None, 0
        for w in (dados or {}).get("results", []):
            s = fuzz.token_sort_ratio(alvo, normalize_title(w.get("display_name")))
            ano = w.get("publication_year")
            if year and ano and abs(int(ano) - int(year)) > 1:
                continue
            if s > melhor_score:
                melhor, melhor_score = w, s
        if melhor is not None and melhor_score >= config.TITULO_MATCH_LIMIAR:
            return self._store(melhor)
        return None


def issns_of(meta) -> set[str]:
    return {normalize_issn(x) for x in str(meta.get("issn") or "").split(",")} - {""}
