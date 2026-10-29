# String de busca: FL auto-supervisionado para HAR

Buscas para começar a curadoria no app (aba **Projeto → consultas OpenAlex**).
Cada consulta busca em **título + abstract**. Cole o texto do bloco de código como está.

Contagens medidas no OpenAlex em 2026-10-29. Elas crescem com o tempo.

## Blocos de sinônimos

Cada bloco junta os nomes que a literatura usa para o mesmo conceito, ligados por `OR`.
As consultas combinam os blocos com `AND`.

**Aprendizado federado (FL)**
```
(federated OR "decentralized learning" OR "decentralised learning")
```
- `federated` sem aspas já cobre "federated learning", "federated training",
  "federated optimization" etc., porque o OpenAlex reduz palavras ao radical.
- Ficou de fora: `"collaborative learning"`. Nos testes, trouxe artigos de educação
  (aprendizagem colaborativa).

**Aprendizado auto-supervisionado (SSL)**
```
("self-supervised" OR "self supervised" OR selfsupervised OR contrastive OR "representation learning" OR "masked autoencoder" OR "masked autoencoders" OR "pretext task" OR "pretext tasks")
```
- `contrastive` cobre "contrastive learning", SimCLR e afins. `masked autoencoder` cobre a
  família de reconstrução mascarada. `pretext task` cobre os métodos antigos (rotação,
  transformações etc.).
- `"representation learning"` é amplo, mas é o termo de artigos-chave como o Meta-HAR
  ("Federated Representation Learning for HAR"). Só fica na consulta principal, onde os
  outros dois blocos filtram o ruído.
- Ficaram de fora do bloco: `semi-supervised` e `unlabeled data`. São um tema vizinho
  (poucos rótulos), mas não são SSL. Têm uma consulta própria abaixo.

**Reconhecimento de atividades humanas (HAR)**
```
("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```
- `HAR` sozinho pega artigos de FL genérico que só usam bases de HAR nos experimentos.
  Isso é útil para conhecer as bases, mas gera algum ruído.
- Ficaram de fora: `"action recognition"` (quase sempre vídeo) e `"sensor-based"` (genérico
  demais).

## Consultas

| # | Consulta | Resultados | Máx. no app | Para qual cesta |
|---|---|---:|---:|---|
| 1 | FL + SSL + HAR (principal) | 67 | 200 | Recentes |
| 2 | FL + HAR | 1.116 | 300 | Recentes |
| 3 | SSL + HAR | 13.460 | 300 | Fundacionais / Recentes |
| 4 | FL + SSL, em geral | 553 | 300 | Fundacionais / Recentes |
| 5 | FL + poucos rótulos + HAR | 39 | 100 | Recentes (comparação) |
| 6 | Surveys (3 consultas) | 167 / 1.860 / 672 | 100 cada | Grande área |

### 1. Principal: FL + SSL + HAR
O núcleo do tema. Nos testes, mais ou menos os 50 primeiros eram relevantes, e o resto
era ruído fácil de excluir na triagem.
```
(federated OR "decentralized learning" OR "decentralised learning") AND ("self-supervised" OR "self supervised" OR selfsupervised OR contrastive OR "representation learning" OR "masked autoencoder" OR "masked autoencoders" OR "pretext task" OR "pretext tasks") AND ("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```

### 2. FL + HAR (sem exigir SSL)
FL supervisionado em HAR: personalização, dados heterogêneos entre usuários, bases
usadas. Serve de linha de base para o seu método.
```
(federated OR "decentralized learning" OR "decentralised learning") AND ("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```

### 3. SSL + HAR (centralizado)
SSL para sensores vestíveis sem FL, como masked reconstruction, contrastive HAR e o
survey de SSL para acelerômetro. Aqui o SSL é o bloco estrito, sem `"representation
learning"`, porque a consulta é grande.
```
("self-supervised" OR "self supervised" OR selfsupervised OR contrastive OR "masked autoencoder" OR "masked autoencoders" OR "pretext task" OR "pretext tasks") AND ("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```

### 4. FL + SSL em geral (qualquer domínio)
Métodos de SSL federado que nasceram em imagem, áudio ou vídeo (FedU, FedEMA, FedCo etc.)
e que você pode adaptar para HAR. Usa expressões exatas, porque a versão com blocos
soltos trazia 3.537 resultados, muitos fora do tema.
```
("federated self-supervised" OR "federated self supervised" OR "federated contrastive" OR "federated unsupervised" OR "federated representation learning" OR "self-supervised federated" OR "contrastive federated" OR "unsupervised federated")
```

### 5. FL + poucos rótulos + HAR
Abordagens vizinhas (semi-supervisionado, pseudo-rótulos) que atacam o mesmo problema
de falta de rótulos. São os concorrentes diretos na comparação.
```
(federated OR "decentralized learning" OR "decentralised learning") AND ("semi-supervised" OR "semi supervised" OR "unlabeled data" OR "unlabelled data" OR "label scarcity" OR "limited labels" OR "few labels") AND ("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```

### 6. Surveys (grande área)
6a. Surveys de FL em HAR
```
(survey OR review OR overview OR tutorial) AND (federated OR "decentralized learning" OR "decentralised learning") AND ("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```
6b. Surveys de SSL em HAR
```
(survey OR review OR overview OR tutorial) AND ("self-supervised" OR "self supervised" OR selfsupervised OR contrastive OR "masked autoencoder" OR "masked autoencoders" OR "pretext task" OR "pretext tasks") AND ("activity recognition" OR "human activity" OR HAR OR "activity classification" OR "wearable sensor" OR "wearable sensors" OR "inertial sensor" OR "inertial sensors" OR "inertial measurement unit" OR accelerometer OR IMU)
```
6c. Surveys de FL + SSL
```
(survey OR review OR overview OR tutorial) AND ("federated self-supervised" OR "federated self supervised" OR "federated contrastive" OR "federated unsupervised" OR "federated representation learning" OR "self-supervised federated" OR "contrastive federated" OR "unsupervised federated")
```

## Como o OpenAlex lê a string

- `AND`, `OR` e `NOT` em maiúsculas. Use parênteses para agrupar.
- Aspas buscam a expressão exata. Hífen conta como espaço: `"self-supervised"` também
  acha "self supervised".
- Palavras sem aspas são reduzidas ao radical: `federated` também acha "federation".
- **Não há curinga** (`*`). Por isso as formas singular e plural aparecem por extenso.
- Vírgulas viram espaço, porque o app usa vírgula como separador de filtros.

## Ordem sugerida

1. Rode a **consulta 1** e faça a triagem. Escolha os recentes mais fortes.
2. Rode as **consultas 2, 4 e 5** para ampliar os recentes e os métodos.
3. Rode o **Snowball** a partir dos selecionados. Os fundacionais muito citados, como os
   primeiros trabalhos de SSL para HAR e o FedAvg, aparecem aqui pela co-citação. A
   consulta 3 só traz os 300 mais relevantes de 13 mil, então ela sozinha não garante esses
   clássicos.
4. Rode as **consultas 6a, 6b e 6c** para preencher a grande área.
