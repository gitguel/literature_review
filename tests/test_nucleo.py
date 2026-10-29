import json
from pathlib import Path

import pandas as pd
import pytest

import config
from curadoria import decisions, pipeline, snowball
from curadoria.bibio import read_bib
from curadoria.dedup import dedup
from curadoria.keys import normalize_doi, normalize_title, paper_key
from curadoria.openalex import reconstruct_abstract, work_to_meta
from curadoria.projeto import Projeto
from curadoria.ranking import Ranker, load_core, load_sjr
from curadoria.scoring import score

BIB = r"""
@article{a1, title={Communication-Efficient Learning of Deep Networks from Decentralized Data},
  author={McMahan, Brendan and Moore, Eider}, year={2017}, journal={AISTATS},
  doi={https://doi.org/10.48550/ARXIV.1602.05629}, abstract={short}}
@inproceedings{a2, title={Communication-efficient learning of deep networks from decentralized data},
  author={McMahan, Brendan}, year={2017}, booktitle={Artificial Intelligence and Statistics},
  abstract={a much longer abstract than the other one}}
@inproceedings{a3, title={Communication Efficient Learning of Deep Network from Decentralised Data},
  year={2017}, booktitle={X}}
@article{a4, title={A {S}imple {F}ramework for Contrastive Learning}, year={2020}, journal={ICML}}
"""


def _df(bib_text, tmp_path):
    p = tmp_path / "scopus.bib"
    p.write_text(bib_text)
    return pd.DataFrame(read_bib(p))


def test_normalizacao():
    assert normalize_doi("https://doi.org/10.1/ABC") == "10.1/abc"
    assert normalize_doi("doi:10.1/x") == "10.1/x"
    assert normalize_doi("nada") == ""
    assert normalize_title("A {S}imple Framework—for \\emph{Contrastive}!") == "a simple framework for contrastive"
    assert paper_key("", "Título É", 2020.0) == "titulo e|2020"


def test_read_bib_fonte_e_campos(tmp_path):
    df = _df(BIB, tmp_path)
    assert set(df["source"]) == {"scopus"}
    assert df.loc[0, "doi"] == "10.48550/arxiv.1602.05629"
    assert df.loc[3, "title"] == "A Simple Framework for Contrastive Learning"


def test_dedup_marca_e_escolhe_canonica(tmp_path):
    df = dedup(_df(BIB, tmp_path))
    assert len(df) == 4                          # nada é apagado
    grupo = df.iloc[:3]
    assert grupo["is_canonical"].sum() == 1
    assert bool(df.loc[0, "is_canonical"])       # o com DOI vence
    assert df.loc[1, "dup_of"] == df.loc[0, "paper_key"]
    assert df.loc[2, "dup_method"] == "titulo_fuzzy"
    assert bool(df.loc[3, "is_canonical"])


def test_decisoes_ultima_vence(tmp_path):
    decisions.append(tmp_path, "cesta", "k1", "recente")
    decisions.append(tmp_path, "cesta", "k1", "excluido", "Fora do tema")
    decisions.append(tmp_path, "cesta", "k2", "talvez")
    lat = decisions.latest(tmp_path, "cesta")
    assert lat["k1"]["value"] == "excluido" and lat["k1"]["note"] == "Fora do tema"
    assert len(decisions.history(tmp_path, "cesta")) == 3


def test_scores_e_sugestao():
    df = pd.DataFrame({
        "title": ["Old classic", "New method", "A survey of things", "Middle"],
        "year": [2016, 2025, 2021, 2023], "citations": [10000, 50, 800, 5],
        "cocitacao": [3, 0, 0, 0], "venue_rank_final": ["", "A*", "", ""],
        "oa_type": ["", "", "", ""],
    })
    s = score(df, ano_ref=2026, anos_recente=3, idade_min_fund=4)
    assert list(s["cesta_sugerida"]) == ["fundacional", "recente", "grande_area", "recente"]
    assert pd.isna(s.loc[0, "score_recente"])
    assert s.loc[1, "score_recente"] > s.loc[3, "score_recente"]


def test_ranking_core_sjr(tmp_path):
    core = tmp_path / "core.csv"
    core.write_text('1,"International Conference on Machine Learning","ICML","CORE2023","A*"\n'
                    '2,"Workshop on Federated Learning","FL-WS","CORE2023","C"\n'
                    '3,"IEEE International Conference on Pervasive Computing and Communications","PERCOM","CORE2023","A*"\n')
    sjr = tmp_path / "sjr.csv"
    sjr.write_text('Rank;Title;Issn;SJR Best Quartile\n1;"IEEE Sensors Journal";"1530437X, 15581748";Q1\n')
    rk = Ranker(load_core(core), load_sjr(sjr))
    assert rk.match_core("Proceedings of the 37th International Conference on Machine Learning (ICML 2020)")["core_rank"] == "A*"
    assert rk.match_core("ICML Workshop on Something") == {}            # workshop não herda
    assert rk.match_core("2021 IEEE Intl. Conference on Pervasive Computing and Communications (PerCom)")["core_rank"] == "A*"
    assert rk.match_sjr("whatever", {"1530437X"})["sjr_method"] == "issn"
    assert rk.match_sjr("IEEE Sensors Journal", set())["sjr_quartil"] == "Q1"


def test_openalex_meta():
    assert reconstruct_abstract({"world": [1], "hello": [0]}) == "hello world"
    m = work_to_meta({"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/X",
                      "display_name": "T", "publication_year": 2020, "type": "article",
                      "cited_by_count": 7, "referenced_works": ["https://openalex.org/W2"],
                      "primary_location": {"source": {"display_name": "J", "type": "journal",
                                                      "issn": ["1234-5678"]}},
                      "authorships": [{"author": {"display_name": "Ana Silva"}}]})
    assert m["openalex_id"] == "W1" and m["doi"] == "10.1/x" and m["entry_type"] == "article"
    assert m["referenced_works"] == ["W2"]


# --- pipeline ponta a ponta com cache (sem rede) -------------------------------
def _cache_work(proj, wid, **kw):
    meta = {"openalex_id": wid, "doi": "", "title": "", "year": 2020, "oa_type": "article",
            "entry_type": "article", "venue": "V", "venue_type": "journal", "issn": "",
            "authors": "A B", "citations": 0, "abstract": "", "keywords": "",
            "referenced_works": [], "url": ""}
    meta.update(kw)
    d = proj.dir / "cache" / "works"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{wid}.json").write_text(json.dumps(meta))


def test_pipeline_offline_e_snowball(tmp_path):
    proj = Projeto.criar("Teste", base=tmp_path)
    (proj.dir / "bib" / "meus.bib").write_text(r"""
@article{n, title={New SSL FL method for HAR}, year={2025}, journal={J}, openalex={W10}}
@article{o, title={Old foundational paper}, year={2015}, journal={J}, openalex={W20}}
""")
    _cache_work(proj, "W10", title="New SSL FL method for HAR", year=2025, citations=30,
                referenced_works=["W20", "W30"])
    _cache_work(proj, "W20", title="Old foundational paper", year=2015, citations=5000)
    _cache_work(proj, "W30", title="Uncollected classic", year=2012, citations=9000, doi="10.9/classic")

    cont = pipeline.run(proj, online=False)
    assert cont == {**cont, "coletados": 2, "unicos": 2, "enriquecidos": 2}

    view = pipeline.load_view(proj)
    k_new = view.loc[view["title"].str.startswith("New"), "paper_key"].iloc[0]
    decisions.append(proj.dir, "cesta", k_new, "recente")
    view = pipeline.load_view(proj)
    old = view[view["title"].str.startswith("Old")].iloc[0]
    assert old["cocitacao"] == 1 and old["cesta_sugerida"] == "fundacional"

    # snowball sem rede: os metadados já estão no cache
    snowball.run_snowball(proj)
    cands = snowball.load_candidatos(proj)
    assert set(cands["openalex_id"]) == {"W20", "W30"}
    assert cands.set_index("openalex_id").loc["W20", "no_corpus"]          # já está no corpus
    snowball.aceitar(proj, "W30", "fundacional")
    view = pipeline.load_view(proj)
    novo = view[view["paper_key"] == "10.9/classic"].iloc[0]
    assert novo["cesta"] == "fundacional" and novo["origem"] == "snowball"

    # reprocessar preserva decisões; apagar derived/ não perde nada
    for f in (proj.dir / "derived").iterdir():
        f.unlink()
    pipeline.run(proj, online=False)
    view = pipeline.load_view(proj)
    assert set(view.loc[view["cesta"] != "pendente", "cesta"]) == {"recente", "fundacional"}
