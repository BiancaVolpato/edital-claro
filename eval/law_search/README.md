# Avaliação da busca na Lei 14.133/2021

Mede se a busca encontra o artigo certo para uma pergunta feita em linguagem comum.

## Arquivos

| Arquivo | O que é |
| --- | --- |
| `questions.json` | 10 perguntas, cada uma com o artigo esperado e a justificativa |
| `RESULTADOS.md` | Relatório gerado: recall@5 por modo de busca e os resultados de cada pergunta |
| `query_embeddings.npz` | Embeddings das perguntas, para a avaliação rodar sem carregar o modelo |

## Como rodar

Com o banco no ar e a lei indexada (veja `data/law/README.md`), a partir de `backend/`:

```bash
uv run python scripts/eval_law_search.py
```

O mesmo critério roda como teste automatizado no CI
(`backend/tests/test_law_search.py`), que falha se o recall@5 ficar abaixo de 0,8.

## Método

- **Métrica:** recall@5. Uma pergunta conta como acerto se algum dispositivo do artigo
  esperado aparece entre os 5 primeiros resultados.
- **Perguntas:** escritas sem copiar o vocabulário da lei ("visitar o local da obra" em
  vez de "avaliação prévia do local de execução"), que é como um usuário perguntaria. O
  artigo esperado de cada uma foi conferido no texto oficial.
- **Modos comparados:** híbrido (o padrão), só vetorial e só por termos.

## Como o resultado evoluiu

Cada linha é uma medição feita durante o desenvolvimento, com as mesmas 10 perguntas.

| Versão | Híbrida | Só vetorial | Só por termos |
| --- | --- | --- | --- |
| 1. Vetorial + full-text nativo do Postgres (`ts_rank_cd`), fusão RRF | 0,70 | 0,70 | 0,60 |
| 2. Termos ponderados por raridade (IDF) e no máximo 2 resultados por artigo | 0,80 | 0,70 | 0,60 |
| 3. Embedding sem os títulos de capítulo e sem o identificador | 0,90 | 0,90 | 0,60 |

O que cada mudança corrigiu:

- **Da 1 para a 2.** O ranking nativo do Postgres não considera a raridade dos termos.
  Palavras como "contrato" e "obra" dominavam, e dispositivos longos venciam. Na pergunta
  sobre a garantia de execução, o art. 98 estava em primeiro lugar na busca vetorial e
  caía para fora dos 5 primeiros na híbrida, empurrado por resultados ruins da busca por
  termos. Além disso, vários incisos de um mesmo artigo ocupavam todas as posições.
- **Da 2 para a 3.** O texto usado no embedding começava com os títulos de capítulo e o
  identificador, iguais para todos os dispositivos de um capítulo, o que diluía o sentido.
  Sem eles, "modalidades de licitação" foi da posição 7 para a 1 e "visita ao local da
  obra" da 6 para a 4 na busca vetorial. Os títulos continuam no texto da busca por
  termos, onde ajudam.

## Limitações

- **São só 10 perguntas.** Cada uma vale 0,1 de recall, então a diferença entre 0,8 e 0,9
  é uma única pergunta. As mudanças acima são gerais (não há regra feita para uma
  pergunta específica), mas foram escolhidas olhando para este mesmo conjunto, então o
  número pode estar otimista. Um conjunto maior e separado seria o próximo passo.
- **Uma pergunta ainda falha:** "Quais são as formas de escolher a proposta vencedora?"
  (art. 33, critérios de julgamento). Nenhum dos dois sinais liga "formas de escolher" a
  "critérios de julgamento".
- **A busca por termos sozinha é fraca (0,60)** com perguntas coloquiais. Ela ajuda na
  ordenação (o MRR da híbrida é maior que o da vetorial), mas quem sustenta o recall é a
  busca vetorial.
- A avaliação é por artigo. Ela não mede se o parágrafo ou inciso exato veio primeiro.
