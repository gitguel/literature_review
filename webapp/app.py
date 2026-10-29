"""Camada web (Flask). Toda a lógica fica em `curadoria/`; aqui só rotas e telas."""
import io
import json
import shutil
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request,
                   send_file, url_for)
from werkzeug.utils import secure_filename

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from curadoria import decisions, graficos, pipeline, snowball  # noqa: E402
from curadoria.bibio import entries_to_bibtex, read_bib, to_entry, write_bib  # noqa: E402
from curadoria.keys import normalize_title  # noqa: E402
from curadoria.openalex import OpenAlexClient  # noqa: E402
from curadoria.projeto import Projeto  # noqa: E402
from curadoria.ranking import QUARTIS, RANKS_CORE  # noqa: E402

app = Flask(__name__)
app.secret_key = "curadoria-local"

# --- tarefas em segundo plano (uma por projeto) ---------------------------------
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def iniciar_tarefa(proj: Projeto, nome: str, fn) -> bool:
    with _lock:
        atual = _jobs.get(proj.id)
        if atual and atual["rodando"]:
            return False
        estado = {"nome": nome, "rodando": True, "msg": "Iniciando…", "erro": "",
                  "inicio": datetime.now().strftime("%H:%M:%S")}
        _jobs[proj.id] = estado

    def progresso(msg):
        estado["msg"] = msg

    def alvo():
        try:
            fn(progresso)
            estado["msg"] = "Concluído"
        except Exception as e:  # noqa: BLE001 - o erro vai para a tela
            estado["erro"] = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        finally:
            estado["rodando"] = False

    threading.Thread(target=alvo, daemon=True).start()
    return True


def reprocessar(proj: Projeto):
    if not iniciar_tarefa(proj, "Reprocessar", lambda pr: pipeline.run(proj, progresso=pr)):
        flash("Já há uma tarefa rodando neste projeto.", "erro")


# --- helpers ---------------------------------------------------------------------
def projeto(pid) -> Projeto:
    p = Projeto(config.PROJETOS_DIR / secure_filename(pid))
    if not (p.dir / "projeto.json").exists():
        abort(404)
    return p


def contagens(proj) -> dict:
    p = proj.derived("contagens.json")
    return json.loads(p.read_text()) if p.exists() else {}


def placar(view, cfg) -> list[dict]:
    """Ocupação de cada cesta frente à cota (a cota orienta, não bloqueia)."""
    out = []
    for c in config.CESTAS:
        n = int((view["cesta"] == c).sum()) if len(view) else 0
        cota = int(cfg["cotas"].get(c, 0))
        out.append({"cesta": c, "label": config.CESTA_LABEL[c], "n": n, "cota": cota,
                    "estado": "acima" if n > cota else ("cheia" if n == cota else "")})
    talvez = int((view["cesta"] == "talvez").sum()) if len(view) else 0
    out.append({"cesta": "talvez", "label": "Talvez", "n": talvez, "cota": None, "estado": ""})
    return out


@app.context_processor
def globais():
    return {"CESTAS": config.CESTAS, "LABEL": config.CESTA_LABEL, "tem_chave": bool(config.OPENALEX_API_KEY)}


@app.template_filter("ano")
def _ano(v):
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return "—"


@app.template_filter("num")
def _num(v):
    try:
        return f"{int(float(v)):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


# --- início ----------------------------------------------------------------------
@app.route("/")
def inicio():
    return render_template("inicio.html", projetos=Projeto.listar())


@app.post("/novo")
def novo():
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Dê um nome ao projeto.", "erro")
        return redirect(url_for("inicio"))
    p = Projeto.criar(nome)
    p.atualizar(pergunta=request.form.get("pergunta", "").strip())
    return redirect(url_for("aba_projeto", pid=p.id))


@app.get("/p/<pid>/status")
def status(pid):
    return jsonify(_jobs.get(pid) or {"rodando": False})


# --- 1. Projeto ----------------------------------------------------------------------
@app.route("/p/<pid>/projeto", methods=["GET", "POST"])
def aba_projeto(pid):
    proj = projeto(pid)
    if request.method == "POST":
        f = request.form
        try:
            proj.atualizar(
                nome=f["nome"].strip() or proj.id,
                pergunta=f.get("pergunta", "").strip(),
                cotas={c: int(f.get(f"cota_{c}", 0)) for c in config.CESTAS},
                anos_recente=int(f["anos_recente"]),
                idade_min_fundacional=int(f["idade_min_fundacional"]),
                ano_referencia=int(f["ano_referencia"]) if f.get("ano_referencia") else None,
                motivos_exclusao=[m.strip() for m in f.get("motivos", "").splitlines() if m.strip()],
                enriquecer="enriquecer" in f,
            )
            flash("Configurações salvas.", "ok")
        except (KeyError, ValueError) as e:
            flash(f"Valor inválido: {e}", "erro")
        return redirect(url_for("aba_projeto", pid=pid))

    bibs = []
    for b in proj.bibs():
        try:
            n = len(read_bib(b))
        except Exception:  # noqa: BLE001
            n = "erro de leitura"
        bibs.append({"nome": b.name, "n": n, "origem": pipeline._origem(b.stem)})
    rk = proj.dir / "rankings"
    return render_template("projeto.html", proj=proj, cfg=proj.cfg, bibs=bibs, cont=contagens(proj),
                           core=(rk / "core.csv").exists(), sjr=(rk / "sjr.csv").exists(),
                           job=_jobs.get(pid), aba="projeto")


@app.post("/p/<pid>/upload")
def upload(pid):
    proj = projeto(pid)
    tipo = request.form.get("tipo", "bib")
    arquivos = [a for a in request.files.getlist("arquivo") if a.filename]
    if not arquivos:
        flash("Nenhum arquivo selecionado.", "erro")
        return redirect(url_for("aba_projeto", pid=pid))
    if tipo in ("core", "sjr"):
        arquivos[0].save(proj.dir / "rankings" / f"{tipo}.csv")
        flash(f"Tabela {tipo.upper()} enviada.", "ok")
    else:
        for a in arquivos:
            nome = secure_filename(a.filename)
            if not nome.lower().endswith(".bib"):
                flash(f"{a.filename}: só arquivos .bib.", "erro")
                continue
            if nome.startswith("openalex_") or nome == "snowball.bib":
                nome = "up_" + nome   # nomes reservados
            a.save(proj.dir / "bib" / nome)
        flash(f"{len(arquivos)} arquivo(s) enviado(s). Reprocessando…", "ok")
    reprocessar(proj)
    return redirect(url_for("aba_projeto", pid=pid))


@app.post("/p/<pid>/remover_arquivo")
def remover_arquivo(pid):
    proj = projeto(pid)
    nome = secure_filename(request.form["nome"])
    alvo = proj.dir / ("rankings" if nome in ("core.csv", "sjr.csv") else "bib") / nome
    if alvo.exists():
        lixeira = proj.dir / "lixeira"
        lixeira.mkdir(exist_ok=True)
        shutil.move(alvo, lixeira / f"{datetime.now():%Y%m%d%H%M%S}_{nome}")
        flash(f"{nome} removido (cópia em lixeira/).", "ok")
        reprocessar(proj)
    return redirect(url_for("aba_projeto", pid=pid))


@app.post("/p/<pid>/reprocessar")
def rota_reprocessar(pid):
    reprocessar(projeto(pid))
    return redirect(url_for("aba_projeto", pid=pid))


@app.post("/p/<pid>/consulta")
def consulta(pid):
    proj = projeto(pid)
    f = request.form
    acao = f.get("acao")
    if acao == "adicionar" and f.get("query", "").strip():
        proj.add_consulta(f["query"], f.get("year_from") or None, f.get("year_to") or None,
                          f.get("max_results") or None)
        flash("Consulta adicionada. Clique em Rodar para buscar.", "ok")
    elif acao == "remover":
        proj.remover_consulta(f["cid"])
        flash("Consulta removida (e o .bib dela).", "ok")
        reprocessar(proj)
    elif acao == "rodar":
        cid = f["cid"]

        def tarefa(pr):
            q = proj.consulta(cid)
            cli = OpenAlexClient(proj.dir / "cache", progresso=pr)
            metas = cli.search(q["query"], q["max_results"], q["year_from"], q["year_to"])
            write_bib(proj.bib_consulta(cid), [to_entry(m) for m in metas])
            cfg = proj.cfg
            for c in cfg["consultas"]:
                if c["id"] == cid:
                    c["ultima_execucao"] = datetime.now().isoformat(timespec="minutes")
                    c["n_resultados"] = len(metas)
            proj.salvar(cfg)
            pr(f"{len(metas)} resultados (~US$ {cli.custo_usd:.4f}). Reprocessando…")
            pipeline.run(proj, progresso=pr)

        if not iniciar_tarefa(proj, "Busca OpenAlex", tarefa):
            flash("Já há uma tarefa rodando neste projeto.", "erro")
    return redirect(url_for("aba_projeto", pid=pid))


# --- 2. Venues ---------------------------------------------------------------------
@app.route("/p/<pid>/venues", methods=["GET", "POST"])
def aba_venues(pid):
    proj = projeto(pid)
    if request.method == "POST":
        f = request.form
        if f.get("tipo") == "venue":
            decisions.append(proj.dir, "venue_rank", normalize_title(f["venue"]), f["rank"], f["venue"])
        elif f.get("tipo") == "recuperacao":
            valor = f["rank"] if f["acao"] == "aceitar" else "rejeitado"
            decisions.append(proj.dir, "rank_recovery", f["key"], valor)
        return redirect(url_for("aba_venues", pid=pid) + "#" + f.get("ancora", ""))

    view = pipeline.load_view(proj)
    sem_rank, manuais, propostas = [], [], []
    if len(view):
        v = view[view["venue"] != ""]
        sem = v[v["rank_pipeline"] == ""]
        g = sem.groupby("venue").agg(n=("paper_key", "size"), manual=("rank_manual", "first"),
                                     sel=("cesta", lambda s: int(s.isin(config.CESTAS).sum())))
        g = g.reset_index().sort_values(["n", "venue"], ascending=[False, True])
        sem_rank = g[g["manual"] == ""].to_dict("records")
        manuais = g[g["manual"] != ""].to_dict("records")
        p = proj.derived("rank_recovery.csv")
        if p.exists():
            props = pd.read_csv(p, dtype=str, keep_default_na=False)
            feitas = decisions.latest(proj.dir, "rank_recovery")
            propostas = [r for r in props.to_dict("records") if r["key"] not in feitas]
    return render_template("venues.html", proj=proj, sem_rank=sem_rank, manuais=manuais,
                           propostas=propostas, ranks=RANKS_CORE + QUARTIS, aba="venues")


# --- 3. Triagem ------------------------------------------------------------------------
FILTROS = {"pendentes": "Pendentes", "grande_area": "Grande área", "fundacional": "Fundacionais",
           "recente": "Recentes", "talvez": "Talvez", "excluido": "Excluídos", "todos": "Todos"}
ORDENS = {"score": "Maior score", "citations": "Mais citados", "cit_ano": "Citações/ano",
          "year_desc": "Mais novos", "year_asc": "Mais antigos"}


def filtrar(view, f, sug, q, ordem):
    if f == "pendentes":
        view = view[view["cesta"] == "pendente"]
    elif f != "todos":
        view = view[view["cesta"] == f]
    if sug:
        view = view[view["cesta_sugerida"] == ("" if sug == "nenhuma" else sug)]
    if q:
        alvo = (view["title"] + " " + view["abstract"] + " " + view["keywords"] + " " + view["venue"]).str.lower()
        for termo in q.lower().split():
            view = view[alvo.loc[view.index].str.contains(termo, regex=False)]
    if ordem == "year_desc":
        return view.sort_values(["year", "score"], ascending=False)
    if ordem == "year_asc":
        return view.sort_values(["year", "score"], ascending=[True, False])
    col = ordem if ordem in ("citations", "cit_ano") else "score"
    return view.sort_values([col, "citations"], ascending=False, na_position="last")


@app.get("/p/<pid>/triagem")
def aba_triagem(pid):
    proj = projeto(pid)
    a = request.args
    f, sug, q, ordem = a.get("f", "pendentes"), a.get("sug", ""), a.get("q", "").strip(), a.get("ordem", "score")
    view = pipeline.load_view(proj)
    lista = filtrar(view, f, sug, q, ordem) if len(view) else view
    i = max(0, min(int(a.get("i", 0) or 0), max(len(lista) - 1, 0)))
    paper = lista.iloc[i].to_dict() if len(lista) else None
    return render_template("triagem.html", proj=proj, cfg=proj.cfg, paper=paper, i=i, total=len(lista),
                           f=f, sug=sug, q=q, ordem=ordem, FILTROS=FILTROS, ORDENS=ORDENS,
                           placar=placar(view, proj.cfg), vazio=view.empty, aba="triagem")


@app.post("/p/<pid>/decidir")
def decidir(pid):
    proj = projeto(pid)
    f = request.form
    cesta = f["cesta"]
    if cesta not in config.CESTAS + ["talvez", "excluido", "pendente"]:
        abort(400)
    motivo = f.get("outro", "").strip() if f.get("motivo") == "__outro" else f.get("motivo", "")
    decisions.append(proj.dir, "cesta", f["key"], cesta, motivo if cesta == "excluido" else f.get("nota", ""))
    destino = f.get("voltar") or url_for("aba_triagem", pid=pid)
    return redirect(destino)


# --- 4. Snowball -----------------------------------------------------------------------
@app.get("/p/<pid>/snowball")
def aba_snowball(pid):
    proj = projeto(pid)
    so_antigos = request.args.get("antigos") == "1"
    mostrar = request.args.get("mostrar", "novos")
    cands = snowball.load_candidatos(proj)
    if len(cands):
        if so_antigos:
            cands = cands[(proj.ano_ref - cands["year"]) >= int(proj.cfg["idade_min_fundacional"])]
        if mostrar == "novos":
            cands = cands[(cands["decisao"] == "") | (cands["decisao"] == "pendente")]
    meta = proj.derived("snowball_meta.txt")
    meta = meta.read_text().split("|") if meta.exists() else None
    view = pipeline.load_view(proj)
    return render_template("snowball.html", proj=proj, cands=cands.head(300).to_dict("records"),
                           n_total=len(cands), meta=meta, so_antigos=so_antigos, mostrar=mostrar,
                           placar=placar(view, proj.cfg), job=_jobs.get(pid), aba="snowball")


@app.post("/p/<pid>/snowball")
def snowball_acao(pid):
    proj = projeto(pid)
    f = request.form
    if f["acao"] == "rodar":
        talvez = "talvez" in f
        if not iniciar_tarefa(proj, "Snowball", lambda pr: snowball.run_snowball(proj, talvez, pr)):
            flash("Já há uma tarefa rodando neste projeto.", "erro")
    elif f["acao"] == "aceitar":
        snowball.aceitar(proj, f["wid"], f["cesta"])
    elif f["acao"] == "ignorar":
        decisions.append(proj.dir, "cesta", f["key"], "excluido", "snowball: ignorado")
    return redirect(f.get("voltar") or url_for("aba_snowball", pid=pid))


# --- 5. Seleção --------------------------------------------------------------------------
def ordenar_cesta(view, cesta):
    s = view[view["cesta"] == cesta].copy()
    s["_o"] = s["ordem"].fillna(1e9)
    return s.sort_values(["_o", "score"], ascending=[True, False])


@app.get("/p/<pid>/selecao")
def aba_selecao(pid):
    proj = projeto(pid)
    filtro = request.args.get("lido", "todos")
    view = pipeline.load_view(proj)
    colunas = {}
    for c in config.CESTAS + ["talvez"]:
        s = ordenar_cesta(view, c) if len(view) else view
        if filtro == "a_ler" and len(s):
            s = s[~s["lido"]]
        elif filtro == "lidos" and len(s):
            s = s[s["lido"]]
        colunas[c] = s.to_dict("records")
    return render_template("selecao.html", proj=proj, colunas=colunas, filtro=filtro,
                           placar=placar(view, proj.cfg), aba="selecao")


@app.post("/p/<pid>/selecao")
def selecao_acao(pid):
    proj = projeto(pid)
    f = request.form
    key = f["key"]
    if f["acao"] == "lido":
        decisions.append(proj.dir, "lido", key, "1" if f.get("valor") == "1" else "0")
    elif f["acao"] in ("subir", "descer"):
        view = pipeline.load_view(proj)
        cesta = view.loc[view["paper_key"] == key, "cesta"].iloc[0]
        chaves = ordenar_cesta(view, cesta)["paper_key"].tolist()
        i = chaves.index(key)
        j = i - 1 if f["acao"] == "subir" else i + 1
        if 0 <= j < len(chaves):
            chaves[i], chaves[j] = chaves[j], chaves[i]
            for pos, k in enumerate(chaves):
                decisions.append(proj.dir, "ordem", k, pos)
    return redirect(url_for("aba_selecao", pid=pid, lido=f.get("filtro", "todos")))


@app.get("/p/<pid>/exportar.<fmt>")
def exportar(pid, fmt):
    proj = projeto(pid)
    qual = request.args.get("cesta", "todas")
    view = pipeline.load_view(proj)
    cestas = config.CESTAS if qual == "todas" else [qual]
    partes = [ordenar_cesta(view, c) for c in cestas] if len(view) else []
    sel = pd.concat(partes) if partes else pd.DataFrame()
    nome = f"{proj.id}_{qual}"
    if fmt == "bib":
        entradas = [to_entry(r, {"cesta": config.CESTA_LABEL[r["cesta"]],
                                 "citacoes_openalex": _num(r["citations"]) if r["citations"] == r["citations"] else ""})
                    for r in sel.to_dict("records")]
        return Response(entries_to_bibtex(entradas), mimetype="application/x-bibtex",
                        headers={"Content-Disposition": f"attachment; filename={nome}.bib"})
    if fmt == "csv":
        cols = ["cesta", "title", "authors", "year", "venue", "venue_rank_final", "citations", "cit_ano",
                "cocitacao", "lido", "origem", "doi", "url", "paper_key"]
        buf = io.StringIO()
        sel.reindex(columns=cols).to_csv(buf, index=False)
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={nome}.csv"})
    abort(404)


# --- 6. Estatísticas ---------------------------------------------------------------------
@app.get("/p/<pid>/estatisticas")
def aba_stats(pid):
    proj = projeto(pid)
    view = pipeline.load_view(proj)
    return render_template("estatisticas.html", proj=proj, cont=contagens(proj),
                           placar=placar(view, proj.cfg), aba="stats",
                           graficos=["funil", "ano", "citacoes", "leitura", "fontes", "venues", "ranks", "motivos"])


@app.get("/p/<pid>/grafico/<nome>.png")
def grafico(pid, nome):
    proj = projeto(pid)
    view = pipeline.load_view(proj)
    if nome == "funil":
        png = graficos.funil(view, contagens(proj))
    elif nome == "ano":
        png = graficos.por_ano(view)
    elif nome == "citacoes":
        png = graficos.citacoes_por_cesta(view)
    elif nome == "leitura":
        png = graficos.leitura(view)
    elif nome == "fontes":
        nomes = {f"openalex_{q['id']}": f"busca: {q['query']}" for q in proj.cfg["consultas"]}
        png = graficos.barras({nomes.get(k, k): v for k, v in contagens(proj).get("por_fonte", {}).items()})
    elif nome == "venues":
        png = graficos.contagem(view["venue"] if len(view) else pd.Series(dtype=str))
    elif nome == "ranks":
        png = graficos.contagem(view["venue_rank_final"].replace("", "sem rank") if len(view) else pd.Series(dtype=str))
    elif nome == "motivos":
        png = graficos.contagem(view.loc[view["cesta"] == "excluido", "motivo"].replace("", "(sem motivo)")
                                if len(view) else pd.Series(dtype=str), cor="#e34948")
    else:
        abort(404)
    return send_file(io.BytesIO(png), mimetype="image/png")


def main():
    config.PROJETOS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=config.FLASK_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
