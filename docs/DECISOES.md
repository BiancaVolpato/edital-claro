# Registro de decisões (ADRs)

Cada decisão relevante do projeto fica registrada aqui em formato curto: contexto, opções
consideradas, escolha e trade-off. As decisões são numeradas e nunca apagadas; quando uma
é revista, a nova entrada aponta para a antiga.

---

## ADR-001: Monorepo com `just` como executor de tarefas

- **Etapa:** 1
- **Contexto:** O projeto tem backend (Python), frontend (Node), avaliação e documentação,
  e precisa de comandos únicos (`dev`, `test`, `lint`, `eval`) que funcionem na máquina de
  desenvolvimento (Windows) e no CI (Linux).
- **Opções:** (a) Makefile; (b) justfile; (c) scripts npm/Python soltos.
- **Escolha:** Monorepo com um `justfile` na raiz.
- **Trade-off:** `make` não vem instalado no Windows e depende de um shell POSIX; `just` é
  um binário único que roda igual nos dois sistemas. O custo é uma ferramenta a mais para
  instalar. As receitas usam um comando por linha para funcionarem tanto em `sh` quanto em
  PowerShell. O CI chama os comandos diretamente, sem depender do `just`.

## ADR-002: SQLAlchemy síncrono com psycopg 3

- **Etapa:** 1
- **Contexto:** O FastAPI aceita rotas síncronas e assíncronas. A escolha do modo de acesso
  ao banco afeta todo o código de persistência e os testes.
- **Opções:** (a) SQLAlchemy síncrono; (b) SQLAlchemy assíncrono (`asyncpg`).
- **Escolha:** Síncrono, com o driver `psycopg` 3.
- **Trade-off:** O gargalo do sistema são as chamadas ao LLM e o processamento de PDF, não
  o banco. O modo síncrono é mais simples de escrever, testar e depurar, e o FastAPI roda
  rotas síncronas em um pool de threads. Perde-se vazão em cenários de muitas conexões
  simultâneas, o que não é o caso de uso aqui. O `psycopg` 3 também suporta modo
  assíncrono, então a migração futura não exige trocar de driver.

## ADR-003: Logging estruturado em JSON com a biblioteca padrão

- **Etapa:** 1
- **Contexto:** Os logs precisam ser legíveis por máquina (uma linha JSON por evento) para
  permitir auditoria de custo, latência e citações inválidas nas etapas seguintes.
- **Opções:** (a) `structlog`; (b) `python-json-logger`; (c) um `Formatter` próprio sobre o
  módulo `logging`.
- **Escolha:** Um `JsonFormatter` próprio (cerca de 20 linhas) em `app/core/logging.py`.
- **Trade-off:** Zero dependências e comportamento totalmente visível no código. Não há
  recursos como contexto ligado automaticamente a cada log (`bind`); os campos extras são
  passados via `extra=`. Se isso passar a incomodar, trocar por `structlog` é localizado.
  Um middleware registra uma linha por requisição com `request_id`, rota, status e duração.
  O `request_id` é sempre gerado pelo servidor: aceitar o valor enviado pelo cliente
  permitiria forjar entradas de log.

## ADR-004: `/health` responde 200 mesmo com o banco fora do ar

- **Etapa:** 1
- **Contexto:** O endpoint de saúde é usado pelo docker-compose, pelo frontend e, depois,
  pelo serviço de deploy para decidir se o processo está vivo.
- **Opções:** (a) retornar 503 quando o banco não responde; (b) retornar sempre 200 e
  informar o estado do banco no corpo; (c) dois endpoints (`/health` e `/ready`).
- **Escolha:** Opção (b): `{"status": "ok", "version": ..., "database": "ok" | "unavailable"}`.
- **Trade-off:** Uma queda do banco fica visível sem fazer o orquestrador reiniciar um
  processo de API saudável (o que não resolveria nada). Quem consome precisa ler o campo
  `database`, não só o código HTTP. Se o deploy exigir uma sonda de prontidão separada,
  cria-se um `/ready` na Etapa 11.
- **Nota:** Com o banco fora do ar, a checagem demora alguns segundos (o tempo limite de
  conexão é de 2 s por endereço, e `localhost` resolve para IPv6 e IPv4). Por isso o
  frontend espera até 10 s pelo `/health`. Um teste manual mostrou que, com um limite menor
  que o do backend, a página informava "API fora do ar" com a API funcionando.

## ADR-005: Migrações aplicadas na subida do container; migração inicial só habilita o pgvector

- **Etapa:** 1
- **Contexto:** O critério de aceite pede que `docker compose up` suba tudo pronto. As
  tabelas do domínio só são definidas a partir da Etapa 2.
- **Opções:** (a) rodar `alembic upgrade head` manualmente; (b) rodar na subida do backend;
  (c) criar as tabelas com `metadata.create_all`.
- **Escolha:** O container do backend roda `alembic upgrade head` antes de iniciar o
  servidor. A migração `0001` contém apenas `CREATE EXTENSION IF NOT EXISTS vector`.
- **Trade-off:** Um único comando deixa o banco pronto e o esquema fica sempre versionado.
  Com várias réplicas do backend subindo ao mesmo tempo haveria corrida entre migrações;
  hoje há uma só instância, e o ponto será revisto no deploy (Etapa 11). O teste da
  migração tem duas camadas: geração do SQL sem banco (roda em qualquer máquina) e
  aplicação em um Postgres real (roda no CI, com `RUN_DB_TESTS=1`).

## ADR-006: Frontend consulta o backend pelo servidor do Next.js

- **Etapa:** 1
- **Contexto:** A página inicial mostra o estado do `/health`. Dentro do docker-compose, o
  navegador enxerga o backend em `localhost:8000`, mas o servidor do Next.js o enxerga em
  `backend:8000`.
- **Opções:** (a) o navegador chama o backend direto (exige CORS e uma variável
  `NEXT_PUBLIC_*` fixada no build); (b) um Server Component faz a chamada no servidor,
  lendo `API_URL` em tempo de execução.
- **Escolha:** Opção (b). O trecho que consulta o backend fica dentro de `<Suspense>`, como
  pede o modelo de cache do Next.js 16 (Cache Components): o restante da página é estático
  e o status é resolvido a cada requisição.
- **Trade-off:** Sem CORS e com a mesma imagem servindo qualquer ambiente. Interações que
  partem do navegador (upload de PDF, acompanhamento do progresso da análise) vão precisar
  de outra rota de acesso; essa decisão fica para a Etapa 8, quando as telas existirem.
- **Nota:** O scaffold foi gerado com as versões atuais (`create-next-app` com Next.js 16 e
  `shadcn` com o estilo padrão, baseado em Base UI). Mantive os padrões das ferramentas em
  vez de fixar versões antigas.
