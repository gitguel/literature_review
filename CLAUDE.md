# Curadoria de literatura

App Flask local para montar a base de leitura do mestrado (Aprendizado Federado
Auto-Supervisionado para HAR): coletar um corpus no OpenAlex e escolher ~25–30 artigos
em três cestas (Grande área, Fundacionais, Recentes). Detalhes de uso no `README.md`.

## Comandos

- Rodar: `.venv/bin/python run.py` → http://127.0.0.1:5000
- Testes: `.venv/bin/python -m pytest -q` (rodam sem rede; devem passar antes de cada commit)

## Estrutura

- `curadoria/`: núcleo (OpenAlex, deduplicação, scoring, snowball, decisões, export)
- `webapp/`: Flask, templates e CSS
- `config.py`: pesos, limiares e cotas. Tudo que é ajustável fica aqui.
- `projetos/`: dados dos projetos do usuário. Fica fora do git.

## Regras

- **Autoria:** todo commit e PR tem só o usuário (`gitguel`) como autor. Não adicione
  `Co-Authored-By`, "Generated with Claude Code" nem qualquer outra menção ao Claude.
- **Segredos:** a `OPENALEX_API_KEY` fica em `.env`, que o `config.py` carrega e que está
  no `.gitignore`. Nunca copie a chave para código, docs ou commits.
- **Perguntas ao usuário:** use a skill `plain-questions`.
- Escreva em português, no mesmo tom do código e da interface.
