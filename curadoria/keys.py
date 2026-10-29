"""Normalização de DOI/título e chave estável de paper."""
import re
import unicodedata

_DOI_PREFIXOS = re.compile(r"^(https?://)?(dx\.)?(doi\.org/)?(doi:\s*)?", re.I)


def normalize_doi(doi) -> str:
    if not isinstance(doi, str) or not doi.strip():
        return ""
    d = _DOI_PREFIXOS.sub("", doi.strip()).strip().lower()
    return d if d.startswith("10.") else ""


def strip_latex(s) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\\[a-zA-Z]+\s*\{([^{}]*)\}", r"\1", s)   # \emph{x} -> x
    s = re.sub(r"\\['`^\"~=.uvHc]\s*\{?([a-zA-Z])\}?", r"\1", s)  # acentos LaTeX
    s = s.replace("{", "").replace("}", "").replace("\\&", "&").replace("~", " ")
    return re.sub(r"\s+", " ", s).strip()


def normalize_title(title) -> str:
    t = strip_latex(title)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def paper_key(doi, title, year) -> str:
    d = normalize_doi(doi)
    if d:
        return d
    y = "" if year is None or year != year else str(int(year))
    return f"{normalize_title(title)}|{y}"


def title_year_key(title, year) -> str:
    y = "" if year is None or year != year else str(int(year))
    return f"{normalize_title(title)}|{y}"


def normalize_issn(issn) -> str:
    s = re.sub(r"[^0-9Xx]", "", str(issn or "")).upper()
    return s if len(s) == 8 else ""
