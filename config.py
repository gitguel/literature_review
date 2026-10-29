"""Constantes e limiares da plataforma. Tudo que é ajustável fica aqui."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Segredos locais (ex.: OPENALEX_API_KEY) em .env, fora do git. O ambiente tem precedência.
_env = BASE_DIR / ".env"
if _env.exists():
    for _linha in _env.read_text().splitlines():
        _k, _sep, _v = _linha.strip().partition("=")
        if _sep and not _k.startswith("#"):
            os.environ.setdefault(_k.strip(), _v.strip().strip('"\''))
PROJETOS_DIR = Path(os.environ.get("CURADORIA_PROJETOS", BASE_DIR / "projetos"))

# --- Cestas ------------------------------------------------------------------
CESTAS = ["grande_area", "fundacional", "recente"]
CESTA_LABEL = {
    "grande_area": "Grande área",
    "fundacional": "Fundacionais",
    "recente": "Recentes / métodos",
    "talvez": "Talvez",
    "excluido": "Excluído",
    "pendente": "Pendente",
}
COTAS_PADRAO = {"grande_area": 5, "fundacional": 10, "recente": 10}

# Janelas de idade (idade = ano_atual - ano). Sem lacuna entre as duas.
ANOS_RECENTE_PADRAO = 3            # recente: idade <= 3
IDADE_MIN_FUNDACIONAL_PADRAO = 4   # fundacional: idade >= 4

MOTIVOS_EXCLUSAO_PADRAO = [
    "Fora do tema",
    "Muito superficial / pouco relevante",
    "Coberto por outro artigo melhor",
    "Venue fraca",
]

# Palavras que marcam um survey/visão geral (procuradas no título)
PALAVRAS_SURVEY = ["survey", "review", "tutorial", "overview", "state of the art",
                   "state-of-the-art", "taxonomy", "challenges and", "open problems",
                   "systematic literature", "advances and open", "future directions",
                   "a primer", "perspectives on", "comprehensive study"]
TIPOS_SURVEY_OPENALEX = {"review"}

# --- Pesos dos scores (cada termo normalizado em 0..1) ---------------------
PESO_GA_CITACOES = 1.0          # grande área: só citações (elegível se survey)
PESO_FUND_CITACOES = 0.6        # fundacional
PESO_FUND_COCITACAO = 0.4
PESO_REC_CIT_ANO = 0.6          # recente
PESO_REC_VENUE = 0.4
BONUS_VENUE = {"A*": 1.0, "A": 1.0, "Q1": 1.0, "B": 0.5, "Q2": 0.5, "C": 0.2, "Q3": 0.2}

# --- Deduplicação ------------------------------------------------------------
DEDUP_FUZZY_LIMIAR = 93         # token_sort_ratio, só dentro do mesmo ano

# --- Rank de venue -----------------------------------------------------------
CORE_FUZZY_LIMIAR = 90
SJR_FUZZY_LIMIAR = 92
PALAVRAS_GENERICAS_VENUE = {
    "international", "conference", "conf", "proceedings", "proc", "ieee", "acm",
    "annual", "symposium", "the", "of", "on", "in", "and", "for", "joint",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "ninth", "tenth", "st", "nd", "rd", "th", "springer", "lecture", "notes",
}

# --- OpenAlex ----------------------------------------------------------------
OPENALEX_URL = "https://api.openalex.org"
# Sem chave, o OpenAlex dá um orçamento diário pequeno compartilhado por IP.
# Chave gratuita em https://openalex.org/settings/api
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "")
OPENALEX_MAILTO = os.environ.get("OPENALEX_MAILTO", "")
OPENALEX_TIMEOUT = 30
OPENALEX_TENTATIVAS = 4
OPENALEX_LOTE = 50              # ids/DOIs por requisição em lote
OPENALEX_POR_PAGINA = 200
CONSULTA_MAX_RESULTADOS_PADRAO = 200
TITULO_MATCH_LIMIAR = 90        # para casar um .bib sem DOI com o OpenAlex

# --- Snowball ----------------------------------------------------------------
SNOWBALL_MAX_CANDIDATOS = 150   # quantos dos mais co-citados buscar metadados
SNOWBALL_MIN_COCITACAO = 1

FLASK_PORT = int(os.environ.get("CURADORIA_PORT", 5000))
