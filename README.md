# Edital Claro

Análise de editais de licitação de obras públicas com IA, em que cada informação extraída
cita a página e o trecho literal do edital de onde veio.

> **Estado atual:** Etapa 3 de 12 concluída. O sistema recebe um edital em PDF, extrai 22
> campos com IA e confere cada citação contra o texto da página. Ainda não há interface
> para a análise (Etapa 8) nem números de qualidade (Etapa 9).

## O problema

Editais de obras públicas são PDFs longos, em linguagem jurídica, e cada órgão escreve de
um jeito.

- **Pequenas construtoras** perdem prazos, deixam passar exigências de habilitação e acabam
  desclassificadas.
- **Prefeituras pequenas** publicam editais com erros ou cláusulas restritivas, que geram
  impugnações.

## O que o sistema vai fazer

1. Receber o PDF de um edital, por upload ou buscando no PNCP (Portal Nacional de
   Contratações Públicas).
2. Extrair os dados estruturados do edital.
3. Gerar um checklist em que cada item cita a página e o trecho literal de origem.
4. Apontar riscos e inconsistências, com fundamentação na Lei 14.133/2021.
5. Comparar o edital com o perfil de uma empresa e dizer se ela está apta a participar e o
   que falta.

## Andamento

| Etapa | Entrega | Estado |
| --- | --- | --- |
| 1 | Fundação do repositório | Concluída |
| 2 | Ingestão de PDF | Concluída |
| 3 | Extração estruturada com citações | Concluída |
| 4 | Base de conhecimento da Lei 14.133 (RAG) | Pendente |
| 5 | Análise de riscos | Pendente |
| 6 | Perfil da empresa e aptidão | Pendente |
| 7 | Integração com o PNCP | Pendente |
| 8 | Frontend | Pendente |
| 9 | Avaliação | Pendente |
| 10 | Segurança, governança e custos | Pendente |
| 11 | Deploy | Pendente |
| 12 | Documentação e apresentação | Pendente |

## Stack

- **Backend:** Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy, Alembic.
- **Banco de dados:** PostgreSQL com pgvector.
- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui.
- **Qualidade:** pytest, ruff, mypy, ESLint, GitHub Actions.

## Como rodar

### Com Docker (tudo de uma vez)

Pré-requisito: Docker Desktop. O passo a passo de instalação no Windows está em
[docs/DOCKER_WSL2.md](docs/DOCKER_WSL2.md).

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

- Frontend: <http://localhost:3000>
- API: <http://localhost:8000/health>
- Documentação interativa da API: <http://localhost:8000/docs>

### Sem Docker (backend e frontend locais)

Pré-requisitos: [uv](https://docs.astral.sh/uv/), Node.js 24 e
[just](https://just.systems/).

```bash
just install
```

Em um terminal:

```bash
just dev-backend
```

Em outro:

```bash
just dev-frontend
```

Sem um PostgreSQL rodando, a API sobe normalmente e o `/health` informa
`"database": "unavailable"`.

## Enviar um edital

Com tudo no ar pelo Docker (`just dev`), envie um dos editais de exemplo:

```bash
curl -F "file=@data/samples/lauro_muller_cc_233_2026.pdf" http://localhost:8000/documents
```

A resposta traz o `id` do documento. O processamento roda em segundo plano; consulte o
resultado trocando `ID` pelo valor recebido:

| Endereço | O que retorna |
| --- | --- |
| `GET /documents/ID` | status (`pending`, `processing`, `ready`, `failed`), metadados e resumo das páginas |
| `GET /documents/ID/pages/4` | texto normalizado da página 4 |
| `GET /documents/ID/chunks` | trechos em ordem de leitura, com título, tipo e páginas |

Os mesmos endpoints podem ser testados pelo navegador em <http://localhost:8000/docs>.
A origem dos editais de exemplo está em [data/samples/README.md](data/samples/README.md).

Páginas escaneadas passam por OCR (Tesseract). A imagem Docker já traz o Tesseract; fora
do Docker, sem ele instalado, essas páginas ficam sem texto e o documento registra um aviso.

## Analisar um edital

A análise chama a API da Anthropic, então precisa de uma chave e tem custo. Coloque a
chave no arquivo `.env` da raiz:

```
ANTHROPIC_API_KEY=sua-chave
```

**Sem Docker**, direto pela linha de comando (não precisa de banco de dados):

```bash
just analyze ../data/samples/lauro_muller_cc_233_2026.pdf
```

O comando mostra cada campo com valor, confiança e páginas citadas, e no fim o total de
citações por estado, os tokens e o custo estimado. Na primeira execução ele baixa o
modelo de embeddings (cerca de 1 GB).

**Com Docker**, pela API: depois de enviar o edital (seção anterior), inicie a análise e
consulte o resultado:

| Endereço | O que faz |
| --- | --- |
| `POST /documents/ID/analyze` | inicia a análise em segundo plano e devolve o `id` dela |
| `GET /analyses/ID_DA_ANALISE` | status, progresso e, ao final, campos, citações, tokens e custo |

Cada campo extraído traz o valor, as citações (página e trecho literal), a confiança e
um indicador de revisão. Cada citação é conferida contra o texto da página e recebe um
estado:

| Estado | Significado |
| --- | --- |
| `valid` | o trecho está na página indicada |
| `wrong_page` | o trecho existe, mas em outra página (a página é corrigida) |
| `not_found` | o trecho não está no documento; o campo é marcado para revisão |
| `too_short` | trecho curto demais para comprovar algo; o campo é marcado para revisão |

## Comandos

| Comando | O que faz |
| --- | --- |
| `just dev` | Sobe Postgres, backend e frontend com Docker |
| `just dev-backend` / `just dev-frontend` | Sobe cada parte localmente, com recarga automática |
| `just test` | Roda os testes do backend (pytest) |
| `just lint` | Roda ruff, mypy, ESLint e o type-check do TypeScript |
| `just fmt` | Formata o código do backend |
| `just migrate` | Aplica as migrações do banco |
| `just analyze ARQUIVO.pdf` | Analisa um edital com o LLM real, sem banco (tem custo) |
| `just eval` | Roda a avaliação (a implementar na Etapa 9) |

## Estrutura

```
backend/    API FastAPI, migrações Alembic e testes
frontend/   Interface Next.js
eval/       Gabarito, scripts e relatórios de avaliação
data/       Editais de exemplo e caches locais
docs/       Decisões de arquitetura e guias
```

## Decisões de arquitetura

As decisões relevantes ficam registradas em [docs/DECISOES.md](docs/DECISOES.md), com
contexto, opções consideradas, escolha e trade-off.

## Aviso

Esta ferramenta é um apoio à leitura de editais e não substitui parecer jurídico.
