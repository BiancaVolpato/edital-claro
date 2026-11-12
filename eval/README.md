# Avaliação

Esta pasta mede, com números, o quanto a extração acerta e onde erra.

| Caminho | O que é |
| --- | --- |
| [ANOTACAO.md](ANOTACAO.md) | guia para anotar o gabarito |
| `golden/` | o gabarito: um JSON por edital com as respostas certas, anotadas à mão |
| `golden/_template.json` | modelo para começar um edital novo |
| [variants.toml](variants.toml) | as variantes comparadas (modelo e estratégia de extração) |
| `runs/` | o resultado bruto de cada variante em cada edital, salvo por `just eval` |
| `RESULTADOS.md` | o relatório gerado por `just eval` |
| `law_search/` | avaliação da busca na Lei 14.133 (Etapa 4) |

## Como rodar

Na raiz do repositório:

```bash
just eval-check
```

confere o gabarito (formato, valores, páginas e o SHA-256 de cada PDF), sem custo.

```bash
just eval
```

roda todas as variantes em todos os editais e escreve `RESULTADOS.md`. Chama o modelo de
verdade: precisa de `ANTHROPIC_API_KEY` no `.env` e tem custo. Para gastar menos:

```bash
just eval --variants opus-secoes --limit 3
```

```bash
just eval --reuse
```

`--reuse` refaz o relatório a partir de `runs/`, sem chamar o modelo (útil depois de
corrigir o gabarito ou mudar uma regra de comparação). Um resultado salvo só é reaproveitado
se tiver sido produzido pelo mesmo prompt e pelo mesmo modelo.

## O que é medido

- **Acurácia por campo:** igualdade exata para datas, valores, opções e estruturas;
  semelhança de texto para órgão, número e objeto. Responder "não informado" quando o
  gabarito é nulo conta como acerto; inventar um valor nesse caso conta como erro.
- **Precisão e recall das exigências de habilitação** (e dos anexos), pareando itens por
  semelhança de texto.
- **Taxa de citações válidas** e se a citação aponta para uma página anotada no gabarito.
- **Custo e tempo médios** por edital.
- **Análise de erros:** valor errado, não encontrado, inventado; quantos erros o sistema
  marcou para revisão; os piores casos.

## No CI

O CI comum roda só os testes das regras de comparação, com um modelo simulado. A avaliação
de verdade roda à mão: no GitHub, Actions > "Avaliação (manual)" > Run workflow, com o
segredo `ANTHROPIC_API_KEY` configurado no repositório. Por padrão ela roda uma variante em
3 editais, e o relatório fica disponível como artefato da execução.
