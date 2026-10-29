"""Um projeto = uma pasta com bib/, decisions/, rankings/, cache/ e derived/."""
import json
import re
import uuid
from datetime import date
from pathlib import Path

import config

SUBPASTAS = ["bib", "decisions", "rankings", "cache", "derived"]


def slug(nome) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", nome.strip().lower()).strip("_")
    return s[:60] or "projeto"


def padrao(nome) -> dict:
    return {
        "nome": nome,
        "pergunta": "",
        "cotas": dict(config.COTAS_PADRAO),
        "anos_recente": config.ANOS_RECENTE_PADRAO,
        "idade_min_fundacional": config.IDADE_MIN_FUNDACIONAL_PADRAO,
        "ano_referencia": None,   # None = ano atual
        "motivos_exclusao": list(config.MOTIVOS_EXCLUSAO_PADRAO),
        "consultas": [],
        "enriquecer": True,
    }


class Projeto:
    def __init__(self, pasta):
        self.dir = Path(pasta)
        self.id = self.dir.name

    # --- ciclo de vida ------------------------------------------------------
    @classmethod
    def criar(cls, nome, base=None):
        base = Path(base or config.PROJETOS_DIR)
        pasta, i = base / slug(nome), 1
        while pasta.exists():
            i += 1
            pasta = base / f"{slug(nome)}_{i}"
        for s in SUBPASTAS:
            (pasta / s).mkdir(parents=True, exist_ok=True)
        p = cls(pasta)
        p.salvar(padrao(nome))
        return p

    @staticmethod
    def listar(base=None) -> list["Projeto"]:
        base = Path(base or config.PROJETOS_DIR)
        if not base.exists():
            return []
        return [Projeto(d) for d in sorted(base.iterdir()) if (d / "projeto.json").exists()]

    # --- configurações --------------------------------------------------------
    @property
    def cfg(self) -> dict:
        dados = json.loads((self.dir / "projeto.json").read_text(encoding="utf-8"))
        return {**padrao(dados.get("nome", self.id)), **dados}

    def salvar(self, cfg: dict):
        (self.dir / "projeto.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                               encoding="utf-8")

    def atualizar(self, **campos):
        c = self.cfg
        c.update(campos)
        self.salvar(c)

    @property
    def ano_ref(self) -> int:
        return int(self.cfg.get("ano_referencia") or date.today().year)

    # --- consultas OpenAlex ----------------------------------------------------
    def add_consulta(self, query, year_from=None, year_to=None, max_results=None):
        c = self.cfg
        c["consultas"].append({
            "id": uuid.uuid4().hex[:8], "query": query.strip(),
            "year_from": year_from or None, "year_to": year_to or None,
            "max_results": int(max_results or config.CONSULTA_MAX_RESULTADOS_PADRAO),
            "ultima_execucao": None, "n_resultados": None,
        })
        self.salvar(c)

    def consulta(self, cid) -> dict | None:
        return next((q for q in self.cfg["consultas"] if q["id"] == cid), None)

    def bib_consulta(self, cid) -> Path:
        return self.dir / "bib" / f"openalex_{cid}.bib"

    def remover_consulta(self, cid):
        c = self.cfg
        c["consultas"] = [q for q in c["consultas"] if q["id"] != cid]
        self.salvar(c)
        self.bib_consulta(cid).unlink(missing_ok=True)

    # --- arquivos ------------------------------------------------------------
    def bibs(self) -> list[Path]:
        return sorted((self.dir / "bib").glob("*.bib"))

    @property
    def snowball_bib(self) -> Path:
        return self.dir / "bib" / "snowball.bib"

    def derived(self, nome) -> Path:
        return self.dir / "derived" / nome
