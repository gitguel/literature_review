# Curadoria de literatura

Aplicação web local (Python + Flask) para montar uma **base de leitura curada**:
coletar um corpus amplo (centenas de candidatos) e escolher ~25–30 artigos em três cestas:

| Cesta | Cota padrão | O que é | Como o app sugere |
|---|---|---|---|
| **Grande área** | 5 | surveys, tutoriais, visões gerais | título/tipo de survey + muitas citações |
| **Fundacionais** | 10 | trabalhos antigos e muito citados até hoje | idade ≥ 4 anos + citações + **co-citação** pelos selecionados |
| **Recentes / métodos** | 10 | estado da arte, venues boas | idade ≤ 3 anos + citações/ano + rank da venue |

As cotas **orientam, não bloqueiam**: passar da cota só gera um aviso, e o corte final acontece na aba Seleção.
O app é genérico, sem nada fixo num tema.

## Como rodar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py          # abre em http://127.0.0.1:5000
```

Opcional, mas recomendado: **chave gratuita do OpenAlex** (<https://openalex.org/settings/api>).
Sem chave, o OpenAlex dá um orçamento diário pequeno compartilhado pelo seu IP: cerca de 100 buscas textuais por dia,
e consultas em lote (por DOI ou id) custam 10× menos. Com chave:

```bash
OPENALEX_API_KEY=suachave .venv/bin/python run.py
```

Outras variáveis: `CURADORIA_PORT` (padrão 5000), `CURADORIA_PROJETOS` (pasta dos projetos; padrão `projetos/`)
e `OPENALEX_MAILTO`.

## Fluxo sugerido

1. **Projeto**: crie o projeto e adicione **várias consultas complementares** ao OpenAlex (busca booleana em título + abstract), por exemplo:
   - `"federated learning" AND ("self-supervised" OR contrastive)`
   - `"federated" AND ("activity recognition" OR HAR)`
   - `("self-supervised" OR contrastive) AND "activity recognition"`
   - `(survey OR review) AND "federated learning"`

   Opcionalmente, envie .bib exportados do Scopus/IEEE/ACM/WoS (o nome do arquivo vira a fonte). Para testar, use os arquivos de `exemplos/`.
2. **Triagem**: um artigo por vez, ordenados pelo maior score, com a cesta sugerida destacada.
   Atalhos: `1` `2` `3` (cestas), `T` (talvez), `X` (excluir), `←` `→` (navegar).
3. **Snowball**: depois de escolher alguns recentes, rode o snowball. As referências citadas por **vários** selecionados
   sobem para o topo; são candidatas naturais a fundacionais. Use "só antigos" para focar nelas.
4. **Venues** (opcional): envie as tabelas CORE/SJR e/ou atribua rank manual às venues sem rank (isso dá bônus aos recentes).
5. **Seleção**: as três cestas lado a lado, com "Talvez" como reserva. Ordene, marque como lido e exporte em BibTeX/CSV.
6. **Estatísticas**: funil, anos, citações por cesta, fontes, venues, ranks, motivos de exclusão e progresso de leitura.

## Dados e reprodutibilidade

```
projetos/<projeto>/
  projeto.json      configurações, cotas e consultas
  bib/              FONTE DE VERDADE: .bib enviados, openalex_<id>.bib (buscas) e snowball.bib
  decisions/        FONTE DE VERDADE: cesta.csv, venue_rank.csv, rank_recovery.csv, ordem.csv, lido.csv
  rankings/         core.csv, sjr.csv (opcionais)
  cache/            respostas do OpenAlex (regenerável, mas economiza orçamento)
  derived/          corpus.csv, snowball.csv, contagens… (regenerável com "Reprocessar")
  lixeira/          .bib removidos
```

- Os logs de decisão são **append-only**: mudar uma decisão grava uma nova linha, e a última vence. As decisões são chaveadas por
  `paper_key` (DOI normalizado ou `título_normalizado|ano`), então sobrevivem a qualquer reprocessamento.
- A deduplicação (DOI → título exato → título fuzzy no mesmo ano) **marca** duplicatas e nunca apaga. A cópia canônica é
  a mais completa (tem DOI > abstract mais longo > primeira encontrada).
- Rank de venue: CORE por sigla, nome exato ou fuzzy só nas palavras distintivas (workshops não herdam o rank da conferência);
  SJR só para periódicos, por ISSN, nome exato ou fuzzy. Quando a cópia canônica não tem rank mas uma duplicata tem, o app gera uma **proposta**
  na aba Venues, que só vale se você aceitar.

## Ajustes

Limiares, pesos dos scores, palavras que indicam survey e limites do snowball ficam em `config.py`.
As janelas de idade e as cotas podem ser mudadas por projeto na aba Projeto.

## Estrutura do código

```
config.py            constantes
curadoria/           pipeline (sem Flask): bibio, keys, dedup, openalex, ranking, scoring,
                     snowball, decisions, pipeline, projeto, graficos
webapp/              Flask: app.py, templates/, static/
tests/               pytest (rodam sem rede)
exemplos/            .bib de exemplo (FL + SSL + HAR)
```

Testes: `.venv/bin/python -m pytest`

## Para depois

Fichamento estruturado por artigo, matriz comparativa de métodos, grafo de citações e mapa de lacunas.
