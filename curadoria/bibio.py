"""Leitura/normalização de .bib e exportação BibTeX/CSV."""
import re
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase

from .keys import normalize_doi, paper_key, strip_latex

CAMPOS = ["paper_key", "source", "bibkey", "entry_type", "title", "authors", "year",
          "venue", "doi", "issn", "abstract", "keywords", "url", "openalex_id"]


def _parse_year(v):
    m = re.search(r"(19|20)\d{2}", str(v or ""))
    return int(m.group(0)) if m else None


def read_bib(path) -> list[dict]:
    """Lê um .bib e devolve registros normalizados; a fonte é o nome do arquivo."""
    path = Path(path)
    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
    parser.homogenize_fields = False
    with open(path, encoding="utf-8", errors="replace") as f:
        db = bibtexparser.load(f, parser=parser)
    registros = []
    for e in db.entries:
        e = {k.lower(): v for k, v in e.items()}
        title = strip_latex(e.get("title", ""))
        if not title:
            continue
        year = _parse_year(e.get("year") or e.get("date"))
        doi = normalize_doi(e.get("doi", "")) or normalize_doi(e.get("url", ""))
        venue = strip_latex(e.get("journal") or e.get("booktitle") or e.get("journaltitle")
                            or e.get("publisher") or e.get("howpublished") or "")
        registros.append({
            "paper_key": paper_key(doi, title, year),
            "source": path.stem,
            "bibkey": e.get("id", ""),
            "entry_type": e.get("entrytype", "misc").lower(),
            "title": title,
            "authors": strip_latex(e.get("author", "")),
            "year": year,
            "venue": venue,
            "doi": doi,
            "issn": e.get("issn", ""),
            "abstract": strip_latex(e.get("abstract", "")),
            "keywords": strip_latex(e.get("keywords") or e.get("author_keywords") or ""),
            "url": e.get("url", ""),
            "openalex_id": e.get("openalex", ""),
        })
    return registros


def _bibkey(rec) -> str:
    primeiro_autor = re.split(r",| and ", str(rec.get("authors") or ""))[0].split()
    sobrenome = re.sub(r"[^A-Za-z]", "", primeiro_autor[-1]) if primeiro_autor else ""
    palavra = next(iter(re.findall(r"[A-Za-z]{4,}", str(rec.get("title", "")))), "paper")
    ano = rec.get("year")
    ano = str(int(float(ano))) if ano not in (None, "") and ano == ano else ""
    return f"{(sobrenome or 'anon').lower()}{ano}{palavra.lower()}"


def to_entry(rec, extra: dict | None = None) -> dict:
    """Converte um registro (dict/Series) em entrada do bibtexparser."""
    def val(k):
        v = rec.get(k, "")
        return "" if v is None or v != v else str(v)

    tipo = val("entry_type") or "misc"
    entry = {"ENTRYTYPE": tipo, "ID": val("bibkey") or _bibkey(rec), "title": val("title")}
    if val("authors"):
        entry["author"] = val("authors")
    if val("year"):
        entry["year"] = str(int(float(val("year"))))
    if val("venue"):
        campo = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle"}
        entry[campo.get(tipo, "howpublished")] = val("venue")
    for k in ["doi", "issn", "abstract", "keywords", "url"]:
        if val(k):
            entry[k] = val(k)
    if val("openalex_id"):
        entry["openalex"] = val("openalex_id")
    for k, v in (extra or {}).items():
        if v not in (None, ""):
            entry[k] = str(v)
    return entry


def entries_to_bibtex(entries: list[dict], ids_existentes=()) -> str:
    vistos, unicas = set(ids_existentes), []
    for e in entries:   # IDs únicos
        base, i = e["ID"], 1
        while e["ID"] in vistos:
            i += 1
            e = {**e, "ID": f"{base}_{i}"}
        vistos.add(e["ID"])
        unicas.append(e)
    db = BibDatabase()
    db.entries = unicas
    w = BibTexWriter()
    w.indent = "  "
    w.order_entries_by = None
    return bibtexparser.dumps(db, w)


def append_entries(path, entries: list[dict]):
    """Acrescenta entradas a um .bib sem reescrever as existentes (usado pelo snowball)."""
    path = Path(path)
    ids = {r["bibkey"] for r in read_bib(path)} if path.exists() else set()
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + entries_to_bibtex(entries, ids))


def write_bib(path, entries: list[dict]):
    Path(path).write_text(entries_to_bibtex(entries), encoding="utf-8")
