"""Gráficos de estatística gerados no servidor (matplotlib → PNG)."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402

# Paleta validada (slots 1-3 passam CVD em todos os pares) + neutros
COR_CESTA = {"grande_area": "#2a78d6", "fundacional": "#eb6834", "recente": "#1baf7a"}
COR_NEUTRA = "#c3c2b7"
TINTA, TINTA_2, GRADE, FUNDO = "#0b0b0b", "#52514e", "#e7e6e1", "#fcfcfb"


def _fig(w=5.0, h=3.0):
    fig, ax = plt.subplots(figsize=(w, h), dpi=130)
    fig.patch.set_facecolor(FUNDO)
    ax.set_facecolor(FUNDO)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRADE)
    ax.tick_params(colors=TINTA_2, labelsize=9, length=0)
    ax.grid(axis="x", color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def _vazio(msg="Sem dados ainda") -> bytes:
    fig, ax = _fig(h=1.2)
    ax.axis("off")
    ax.text(0.5, 0.5, msg, ha="center", va="center", color=TINTA_2, fontsize=10)
    return _png(fig)


def _barh(rotulos, valores, cor=COR_NEUTRA, titulo=None):
    fig, ax = _fig(h=max(1.4, 0.28 * len(rotulos) + 0.7))
    y = range(len(rotulos))[::-1]
    ax.barh(list(y), valores, color=cor, height=0.6, edgecolor=FUNDO, linewidth=1)
    ax.set_yticks(list(y), [str(r)[:38] + ("…" if len(str(r)) > 38 else "") for r in rotulos], color=TINTA)
    ax.grid(axis="y", visible=False)
    for yi, v in zip(y, valores):
        ax.text(v, yi, f" {v}", va="center", fontsize=8, color=TINTA_2)
    if titulo:
        ax.set_title(titulo, loc="left", fontsize=10, color=TINTA)
    return _png(fig)


def funil(view: pd.DataFrame, cont: dict) -> bytes:
    if view.empty:
        return _vazio()
    etapas = {
        "Coletados (todas as fontes)": cont.get("coletados", len(view)),
        "Únicos (após dedup)": len(view),
        "Triados": int((view["cesta"] != "pendente").sum()),
        "Selecionados": int(view["cesta"].isin(config.CESTAS).sum()),
    }
    return _barh(list(etapas), list(etapas.values()), cor="#2a78d6")


def por_ano(view: pd.DataFrame) -> bytes:
    if view.empty or view["year"].isna().all():
        return _vazio()
    anos = view["year"].dropna().astype(int)
    idx = range(anos.min(), anos.max() + 1)
    fig, ax = _fig()
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRADE, linewidth=0.8)
    base = pd.Series(0, index=idx)
    for c in config.CESTAS:
        s = view.loc[view["cesta"] == c, "year"].dropna().astype(int).value_counts().reindex(idx, fill_value=0)
        ax.bar(list(idx), s, bottom=base, color=COR_CESTA[c], width=0.8, edgecolor=FUNDO,
               linewidth=1, label=config.CESTA_LABEL[c])
        base += s
    resto = anos.value_counts().reindex(idx, fill_value=0) - base
    ax.bar(list(idx), resto, bottom=base, color=COR_NEUTRA, width=0.8, edgecolor=FUNDO,
           linewidth=1, label="Demais do corpus")
    ax.legend(frameon=False, fontsize=8, labelcolor=TINTA_2, loc="upper left")
    ax.set_ylabel("artigos", color=TINTA_2, fontsize=8)
    return _png(fig)


def citacoes_por_cesta(view: pd.DataFrame) -> bytes:
    sel = view[view["cesta"].isin(config.CESTAS) & view["citations"].notna()]
    if sel.empty:
        return _vazio("Selecione artigos para ver este gráfico")
    fig, ax = _fig(h=2.6)
    ax.set_xscale("symlog", linthresh=10)
    for i, c in enumerate(config.CESTAS):
        v = sel.loc[sel["cesta"] == c, "citations"]
        ax.scatter(v, [len(config.CESTAS) - 1 - i] * len(v), s=40, color=COR_CESTA[c],
                   edgecolor=FUNDO, linewidth=1.5, zorder=3)
    ax.set_yticks(range(len(config.CESTAS))[::-1], [config.CESTA_LABEL[c] for c in config.CESTAS],
                  color=TINTA)
    ax.set_xlabel("citações (OpenAlex, escala log)", color=TINTA_2, fontsize=8)
    ax.set_ylim(-0.6, len(config.CESTAS) - 0.4)
    return _png(fig)


def contagem(serie: pd.Series, top=15, cor=COR_NEUTRA) -> bytes:
    serie = serie[serie.astype(str).str.strip() != ""]
    if serie.empty:
        return _vazio()
    vc = serie.value_counts().head(top)
    return _barh(vc.index.tolist(), vc.values.tolist(), cor=cor)


def barras(d: dict, cor=COR_NEUTRA) -> bytes:
    if not d:
        return _vazio()
    itens = sorted(d.items(), key=lambda kv: -kv[1])
    return _barh([k for k, _ in itens], [v for _, v in itens], cor=cor)


def leitura(view: pd.DataFrame) -> bytes:
    sel = view[view["cesta"].isin(config.CESTAS)]
    if sel.empty:
        return _vazio("Selecione artigos para ver este gráfico")
    fig, ax = _fig(h=2.2)
    rot = [config.CESTA_LABEL[c] for c in config.CESTAS][::-1]
    for i, c in enumerate(config.CESTAS[::-1]):
        s = sel[sel["cesta"] == c]
        lidos, total = int(s["lido"].sum()), len(s)
        ax.barh(i, total, color=COR_NEUTRA, height=0.55)
        ax.barh(i, lidos, color=COR_CESTA[c], height=0.55)
        ax.text(total, i, f"  {lidos}/{total} lidos", va="center", fontsize=8, color=TINTA_2)
    ax.set_yticks(range(len(rot)), rot, color=TINTA)
    ax.grid(axis="y", visible=False)
    return _png(fig)
