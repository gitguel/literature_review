import time
from pathlib import Path

import config
from webapp import app as webapp

EXEMPLOS = Path(__file__).resolve().parent.parent / "exemplos"


def _esperar(pid):
    for _ in range(100):
        j = webapp._jobs.get(pid)
        if j and not j["rodando"]:
            assert not j["erro"], j["erro"]
            return
        time.sleep(0.1)
    raise AssertionError("tarefa não terminou")


def test_fluxo_web_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJETOS_DIR", tmp_path)
    c = webapp.app.test_client()
    pid = c.post("/novo", data={"nome": "Teste Web"}).headers["Location"].split("/")[2]
    from curadoria.projeto import Projeto
    Projeto(tmp_path / pid).atualizar(enriquecer=False)       # sem rede

    with open(EXEMPLOS / "exemplo_fl_ssl_har.bib", "rb") as a, open(EXEMPLOS / "scopus_exemplo.bib", "rb") as b:
        c.post(f"/p/{pid}/upload", data={"tipo": "bib", "arquivo": [(a, "a.bib"), (b, "b.bib")]},
               content_type="multipart/form-data")
    _esperar(pid)

    for aba in ["projeto", "venues", "triagem", "snowball", "selecao", "estatisticas"]:
        assert c.get(f"/p/{pid}/{aba}").status_code == 200, aba

    html = c.get(f"/p/{pid}/triagem").get_data(as_text=True)
    assert "1 de 13" in html                                     # 16 registros → 13 únicos
    key = html.split('name="key" value="')[1].split('"')[0]
    c.post(f"/p/{pid}/decidir", data={"key": key, "cesta": "recente"})
    c.post(f"/p/{pid}/selecao", data={"acao": "lido", "key": key, "valor": "1"})
    assert "1 de 12" in c.get(f"/p/{pid}/triagem").get_data(as_text=True)

    bib = c.get(f"/p/{pid}/exportar.bib").get_data(as_text=True)
    assert bib.count("@") == 1 and "Recentes" in bib
    for g in ["funil", "ano", "citacoes", "leitura", "fontes", "venues", "ranks", "motivos"]:
        assert c.get(f"/p/{pid}/grafico/{g}.png").data[:4] == b"\x89PNG"
