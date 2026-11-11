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

## ADR-007: Extração com PyMuPDF e OCR apenas nas páginas sem texto

- **Etapa:** 2
- **Contexto:** Todo o resto do sistema depende de saber em que página está cada trecho.
  A maioria dos editais tem texto nativo, mas alguns trazem páginas escaneadas.
- **Opções:** (a) OCR no documento inteiro; (b) texto nativo com PyMuPDF e OCR só onde não
  há texto; (c) ignorar páginas escaneadas.
- **Escolha:** Opção (b). Uma página com menos de 20 caracteres é tratada como sem texto e
  só ela vai para o `ocrmypdf` (Tesseract em português), rodando em um subprocesso com
  tempo limite. O mecanismo de OCR fica atrás de um protocolo (`OcrEngine`).
- **Trade-off:** O texto nativo é exato e leva menos de 2 s em 88 páginas; OCR é lento e
  erra caracteres, então fica restrito ao necessário. O limite de 20 caracteres não pega
  páginas com camada de texto ruim (por exemplo, um escaneado com OCR antigo embutido).
  Quando o OCR não está instalado ou falha, a ingestão **não** falha: a página fica vazia
  e o documento registra um aviso em `metadata.warnings`, para que a ausência de texto
  seja visível e não silenciosa. Cada página guarda se veio de OCR (`ocr`), o que permite
  tratar citações dessas páginas com mais cautela nas próximas etapas.

## ADR-008: Normalização conservadora, preservando as quebras de linha

- **Etapa:** 2
- **Contexto:** O texto extraído traz ruído de layout que atrapalha a busca e a validação
  de citações: caracteres invisíveis, palavras hifenizadas na quebra de linha, cabeçalhos
  e números de página repetidos. Nos editais de exemplo apareceram espaços de largura
  zero no meio de títulos e o número da página no topo de todas as páginas.
- **Opções:** (a) guardar o texto bruto; (b) normalizar de forma agressiva, juntando as
  linhas em parágrafos; (c) normalizar só o que é ruído, mantendo as linhas.
- **Escolha:** Opção (c). Remove caracteres invisíveis e espaços repetidos; junta palavras
  hifenizadas apenas quando a linha seguinte começa com minúscula; remove linhas que se
  repetem em pelo menos metade das páginas, olhando só as 3 primeiras e as 3 últimas
  linhas de cada página e ignorando dígitos (o que cobre "Página 3 de 80").
- **Trade-off:** Manter as quebras de linha é o que permite reconhecer títulos de
  cláusula. Riscos assumidos: uma palavra composta quebrada exatamente no hífen
  ("técnico-" no fim da linha e "profissional" na seguinte) perde o hífen; documentos com
  menos de 4 páginas não têm cabeçalhos removidos, por falta de evidência; uma linha de
  conteúdo que se repita no topo de metade das páginas seria removida. Só o texto
  normalizado é guardado; o PDF original fica armazenado e pode ser reprocessado se as
  regras mudarem.

## ADR-009: Chunking pela estrutura do edital, com regras e não com IA

- **Etapa:** 2
- **Contexto:** A extração (Etapa 3) vai localizar seções relevantes por busca. Chunks que
  cortam uma cláusula ao meio ou misturam o edital com a minuta do contrato pioram a
  busca e as citações.
- **Opções:** (a) janelas de tamanho fixo com sobreposição; (b) pedir a um LLM para
  segmentar; (c) regras que reconhecem títulos ("5. DA HABILITAÇÃO", "CLÁUSULA NONA",
  "ANEXO II") e dividem seções longas nos subitens ("5.1.").
- **Escolha:** Opção (c), com limite de 2.000 caracteres por chunk e divisão por tamanho
  como reserva quando nenhum título é reconhecido. Cada chunk guarda página inicial e
  final, o título da seção e o tipo (`preamble`, `clause`, `annex`). Dentro de um anexo, o
  título carrega o anexo como prefixo ("ANEXO II – MINUTA DO CONTRATO › CLÁUSULA NONA").
- **Trade-off:** Regras são determinísticas, gratuitas, testáveis e rodam em milissegundos;
  um LLM custaria tokens em toda ingestão e poderia alterar o texto. O custo é que cada
  órgão formata de um jeito e algum título vai escapar: nesse caso o texto continua
  presente, apenas agrupado na seção anterior. As regras foram ajustadas em dois editais
  reais e evitam os falsos positivos encontrados neles (linhas de tabela como
  "01 - BSTC D=0,40M", listas de anexos, frases que começam com número). O limite de
  2.000 caracteres existe porque o modelo de embeddings previsto
  (`multilingual-e5-base`) lê no máximo 512 tokens. O tipo `annex` permite distinguir, por
  exemplo, a garantia exigida no edital da garantia descrita na minuta do contrato.

## ADR-010: Ingestão em segundo plano e deduplicação por hash

- **Etapa:** 2
- **Contexto:** Processar um edital leva de menos de um segundo (texto nativo) a minutos
  (muitas páginas com OCR). O mesmo edital pode ser enviado mais de uma vez.
- **Opções:** (a) processar dentro da requisição; (b) `BackgroundTasks` do FastAPI;
  (c) fila com worker separado (Celery, RQ).
- **Escolha:** Opção (b). `POST /documents` grava o arquivo, responde `202` com o
  documento em `pending` e processa em segundo plano; o cliente consulta
  `GET /documents/{id}` até o status virar `ready` ou `failed`. O arquivo é identificado
  pelo SHA-256 do conteúdo: reenviar o mesmo PDF devolve o registro existente (`200`,
  `duplicate: true`) sem reprocessar, exceto se o processamento anterior falhou.
- **Trade-off:** Não exige infraestrutura nova e o contrato da API já é assíncrono, então
  trocar por uma fila depois não muda o cliente. A limitação é que a tarefa roda no
  processo da API: se ele reiniciar no meio, o documento fica preso em `processing` (não
  há retomada automática). O PDF é salvo com o hash como nome; o nome enviado pelo
  cliente é guardado só como rótulo e nunca compõe um caminho. O upload já recusa
  arquivos sem a assinatura de PDF e os maiores que 50 MB; a revisão completa de
  segurança do upload fica na Etapa 10.

## ADR-011: Testes em SQLite na máquina local e em PostgreSQL no CI

- **Etapa:** 2
- **Contexto:** Os testes da API precisam de banco, e a máquina de desenvolvimento ainda
  não tem Docker nem PostgreSQL.
- **Opções:** (a) exigir PostgreSQL para rodar qualquer teste; (b) simular o banco;
  (c) rodar a mesma suíte em SQLite em memória localmente e em PostgreSQL no CI.
- **Escolha:** Opção (c). Com `RUN_DB_TESTS=1` (CI) os testes usam o PostgreSQL com as
  migrações aplicadas; sem a variável, usam SQLite criado a partir dos modelos.
- **Trade-off:** `just test` funciona em qualquer máquina, e o CI garante o comportamento
  no banco real. Para isso os modelos desta etapa usam só tipos portáveis (JSON vira
  JSONB apenas no PostgreSQL). Isso deixa de valer na Etapa 4: colunas `vector` e busca
  full-text só existem no PostgreSQL, e os testes dessas partes vão exigir o banco real.
  Como as migrações são escritas à mão, um teste no CI compara o banco migrado com os
  modelos e falha se houver diferença.
