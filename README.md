# Edital Claro

Análise de editais de licitação de obras públicas com IA, em que cada informação extraída
cita a página e o trecho literal do edital de onde veio.

> **Estado atual:** Etapa 1 de 12 concluída (fundação do repositório). Ainda não há análise
> de editais; o que existe é o esqueleto que roda, com testes e CI.

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
| 2 | Ingestão de PDF | Pendente |
| 3 | Extração estruturada com citações | Pendente |
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

## Comandos

| Comando | O que faz |
| --- | --- |
| `just dev` | Sobe Postgres, backend e frontend com Docker |
| `just dev-backend` / `just dev-frontend` | Sobe cada parte localmente, com recarga automática |
| `just test` | Roda os testes do backend (pytest) |
| `just lint` | Roda ruff, mypy, ESLint e o type-check do TypeScript |
| `just fmt` | Formata o código do backend |
| `just migrate` | Aplica as migrações do banco |
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
