# Edital Claro

Análise de editais de licitação de obras públicas com IA, em que cada informação extraída
cita a página e o trecho literal do edital de onde veio.

> **Estado atual:** Etapa 10 de 12 concluída. Pela interface web, o sistema busca editais no
> PNCP ou recebe um PDF, extrai 22 campos com IA conferindo cada citação, aponta riscos com
> fundamentação na Lei 14.133/2021 e compara as exigências de habilitação com o perfil de
> uma empresa. Clicar numa citação abre o PDF na página e destaca o trecho. A avaliação
> contra um gabarito anotado à mão está pronta (`just eval`); os números dependem do
> gabarito completo.

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
| 4 | Base de conhecimento da Lei 14.133 (RAG) | Concluída |
| 5 | Análise de riscos | Concluída |
| 6 | Perfil da empresa e aptidão | Concluída |
| 7 | Integração com o PNCP | Concluída |
| 8 | Frontend | Concluída |
| 9 | Avaliação | Concluída (aguarda o gabarito) |
| 10 | Segurança, governança e custos | Concluída |
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

## Usar pela interface

Com backend e frontend no ar, abra <http://localhost:3000>. Todo o fluxo funciona pelo
navegador:

1. **Início:** envie o PDF de um edital ou busque no PNCP (período, UF, município e palavras
   do objeto) e clique em "Importar edital".
2. **Documento:** acompanhe a leitura do PDF e clique em "Analisar com IA" (precisa da chave
   da API no `.env`).
3. **Análise:** a barra mostra o andamento. Ao terminar, a tela tem duas colunas:
   - à esquerda, as abas Campos (com a confiança de cada um; os de baixa confiança aparecem
     como "Revisar"), Checklist de habilitação e Riscos (para a empresa ou para o órgão);
   - à direita, o PDF do edital. Clicar numa citação ("p. 5") abre a página e destaca o
     trecho.
   - "Exportar Markdown" baixa o relatório; "Imprimir ou salvar PDF" usa a impressão do
     navegador.
4. **Aptidão:** escolha um perfil de empresa e veja, exigência por exigência, o que atende,
   o que não atende e o que verificar, com o que falta e os prazos críticos.
5. **Perfis de empresa:** cadastre porte, CNAEs, capital, patrimônio, registro no conselho,
   certidões e atestados.
6. **Sobre e limitações:** o que a ferramenta faz e o que não faz.

O navegador fala só com o frontend, que repassa as chamadas para a API (`/api/...`). O
endereço da API vem de `API_URL`.

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
| `GET /documents/ID/file` | o PDF original |

Os mesmos endpoints podem ser testados pelo navegador em <http://localhost:8000/docs>.
A origem dos editais de exemplo está em [data/samples/README.md](data/samples/README.md).

Páginas escaneadas passam por OCR (Tesseract). A imagem Docker já traz o Tesseract; fora
do Docker, sem ele instalado, essas páginas ficam sem texto e o documento registra um aviso.

## Buscar e importar editais do PNCP

O sistema busca contratações publicadas no PNCP (Portal Nacional de Contratações Públicas)
e importa o edital direto de lá, sem precisar baixar e enviar o PDF.

Buscar obras de pavimentação publicadas em SC entre 1º e 10 de novembro:

```
http://localhost:8000/pncp/search?data_inicial=2026-11-01&data_final=2026-11-10&uf=SC&q=pavimentação
```

| Parâmetro | Significado |
| --- | --- |
| `data_inicial`, `data_final` | período de publicação no PNCP (até 365 dias) |
| `uf` | sigla da UF |
| `municipio` ou `codigo_ibge` | nome do município, ou seu código IBGE de 7 dígitos |
| `modalidade` | código de modalidade do PNCP; pode repetir. Padrão: 4 e 5 (concorrências) |
| `q` | palavras que devem aparecer no objeto, sem diferenciar acentos |
| `limite` | quantos resultados devolver (padrão 50) |

Cada resultado traz o número de controle PNCP (ex.: `82939422000191-1-000153/2026`), o
órgão, o município, o objeto, o valor estimado e o período de propostas. Para importar:

```bash
curl -H "Content-Type: application/json" -d '{"numero_controle": "82939422000191-1-000153/2026"}' http://localhost:8000/pncp/import
```

A importação baixa o arquivo do tipo Edital da contratação (ou outro, com
`"sequencial_documento": N`) e o processa como um upload. A resposta traz o `id` do
documento; quando ele estiver `ready`, inicie a análise com `POST /documents/ID/analyze`
(seção seguinte). Importar de novo a mesma contratação não baixa o arquivo outra vez.

A API do PNCP não busca por texto, então o sistema lê as páginas do período e filtra o
objeto aqui. As respostas ficam guardadas por 1 hora em `data/cache/pncp`, e há uma pausa
de 1 segundo entre requisições ao PNCP. Arquivos ZIP não são abertos; nesse caso, baixe-os
no PNCP e envie os PDFs pelo upload.

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

O comando mostra cada campo com valor, confiança e páginas citadas, os riscos
encontrados e, no fim, o total de citações por estado, os tokens e o custo estimado. Na
primeira execução ele baixa o modelo de embeddings (cerca de 1 GB).

Para rodar todos os testes com PostgreSQL, use um banco vazio só para testes: a suíte
apaga documentos e o índice da lei ao terminar, e por isso se recusa a rodar num banco
que já tenha dados.

```bash
RUN_DB_TESTS=1 DATABASE_URL=postgresql+psycopg://usuario:senha@localhost:5432/edital_test just test
```

**Com Docker**, pela API: depois de enviar o edital (seção anterior), inicie a análise e
consulte o resultado:

| Endereço | O que faz |
| --- | --- |
| `POST /documents/ID/analyze` | inicia a análise em segundo plano e devolve o `id` dela |
| `GET /analyses/ID_DA_ANALISE` | status, progresso e, ao final, campos, citações, tokens e custo |
| `GET /analyses` | as análises mais recentes (filtro opcional `document_id`) |
| `GET /analyses/ID_DA_ANALISE/audit` | a trilha de auditoria: prompts, modelos, chamadas, custo e limite |
| `GET /analyses/ID_DA_ANALISE/report.md` | o relatório em Markdown (`audience=licitante` ou `orgao`) |

Cada campo extraído traz o valor, as citações (página e trecho literal), a confiança e
um indicador de revisão. Cada citação é conferida contra o texto da página e recebe um
estado:

| Estado | Significado |
| --- | --- |
| `valid` | o trecho está na página indicada |
| `wrong_page` | o trecho existe, mas em outra página (a página é corrigida) |
| `not_found` | o trecho não está no documento; o campo é marcado para revisão |
| `too_short` | trecho curto demais para comprovar algo; o campo é marcado para revisão |

## Riscos do edital

A análise aponta riscos em duas camadas:

- **Regras**, para o que a lei define em números ou datas: prazo mínimo entre a
  publicação e a abertura, prazo de impugnação, limites de garantia de proposta e
  contratual, capital ou patrimônio mínimo, visita técnica obrigatória, vedação a
  consórcio e datas de abertura divergentes.
- **IA com a lei como referência**, para o que exige interpretação: exigências de
  qualificação técnica ou econômica possivelmente restritivas e outras restrições à
  competição. Para cada tema, o sistema busca os artigos pertinentes da Lei 14.133 e só
  aceita riscos que citem esses artigos.

Todo risco traz o trecho do edital (conferido contra o texto da página), o artigo da lei
com o texto oficial, a severidade (baixa, média, alta) e a origem (regra ou IA). Achados
da IA sem trecho comprovado ou sem artigo recuperado são descartados e listados à parte.

| Endereço | O que retorna |
| --- | --- |
| `GET /analyses/ID` | o resultado completo, com `risks.risks`, `risks.discarded` e `risks.warnings` |
| `GET /analyses/ID/risks?audience=licitante` | os riscos com a orientação para a empresa licitante |
| `GET /analyses/ID/risks?audience=orgao` | os riscos com o alerta para o órgão ("isto pode gerar impugnação") |

Pela linha de comando, sem banco, com vários editais de uma vez:

```bash
just analyze ../data/samples/*.pdf
```

Ao final, o comando confere se todo risco de todos os editais tem citação e artigo válidos.

## Verificar a aptidão de uma empresa

Com uma análise concluída, cadastre o perfil da empresa e compare-o com as exigências de
habilitação do edital. Há um perfil fictício pronto em
[data/profiles/construtora_exemplo.json](data/profiles/construtora_exemplo.json).

```bash
curl -H "Content-Type: application/json" -d @data/profiles/construtora_exemplo.json http://localhost:8000/profiles
```

```bash
curl -H "Content-Type: application/json" -d '{"profile_id": "ID_DO_PERFIL"}' http://localhost:8000/analyses/ID_DA_ANALISE/eligibility
```

| Endereço | O que faz |
| --- | --- |
| `POST /profiles` | cadastra um perfil |
| `GET /profiles` e `GET /profiles/ID` | lista os perfis ou mostra um |
| `PUT /profiles/ID` | substitui o perfil |
| `DELETE /profiles/ID` | apaga o perfil (as verificações já feitas ficam guardadas) |
| `POST /analyses/ID/eligibility` | compara o perfil com o edital e devolve o relatório |
| `GET /eligibility/ID` e `GET /eligibility/ID/report.md` | uma verificação já feita, em JSON ou Markdown |

O perfil traz porte (ME, EPP ou demais), CNAEs, capital social, patrimônio líquido,
atestados técnicos (com os serviços, quantidades e unidades), certidões com validade e
registro no CREA ou CAU.

O relatório tem um resultado para cada exigência extraída do edital, com o trecho e a
página de origem:

| Resultado | Significado |
| --- | --- |
| `atende` | o perfil cumpre a exigência |
| `nao_atende` | o perfil não cumpre (por exemplo, certidão que vence antes da abertura) |
| `nao_verificavel` | o perfil não tem o dado, ou a exigência não pôde ser lida; conferir à mão |

O resumo traz o veredito (`apto`, `apto_com_ressalvas` ou `inapto`), o que falta e os prazos
críticos: abertura, impugnação, esclarecimentos e certidões a renovar.

Datas, valores e quantidades são comparados por código. A IA só diz quais atestados são do
mesmo tipo de serviço que a exigência, e nem vê as quantidades executadas: a soma e a
comparação com o mínimo são feitas depois, por código. Sem chave da API, a verificação roda
do mesmo jeito e só os atestados ficam como `nao_verificavel`.

## Avaliação da extração

A extração é medida contra um gabarito anotado à mão (`eval/golden/`, um JSON por edital),
em quatro variantes: três modelos com extração por seções e um com extração direta do
documento. O relatório traz acurácia por campo, precisão e recall das exigências de
habilitação, taxa de citações válidas, custo e tempo por edital, os piores casos e uma
análise de erros.

| Indicador | Resultado |
| --- | --- |
| Acurácia dos campos | a medir |
| Exigências de habilitação (precisão / recall) | a medir |
| Citações válidas | a medir |
| Custo e tempo médios por edital | a medir |

Os números entram aqui depois da primeira rodada com o gabarito completo (15 a 20 editais).
Como anotar: [eval/ANOTACAO.md](eval/ANOTACAO.md). Como rodar e o que cada número significa:
[eval/README.md](eval/README.md).

## Buscar na Lei 14.133/2021

A lei está dividida em 1.410 dispositivos (artigos, parágrafos, incisos e alíneas), cada
um com seu identificador ("Art. 67, § 1º") e o capítulo a que pertence. A busca combina
semelhança de sentido (embeddings) com correspondência de termos.

Com o Docker no ar, a lei já é indexada na subida do backend. Consulte pelo navegador:

```
http://localhost:8000/law/search?q=prazo para impugnar o edital
```

| Parâmetro | Significado |
| --- | --- |
| `q` | a pergunta ou o tema |
| `k` | quantos resultados (padrão 5, máximo 20) |
| `mode` | `hybrid` (padrão), `vector` ou `lexical` |

Em 10 perguntas de teste, o artigo esperado aparece entre os 5 primeiros resultados em 9
(recall@5 de 0,90). O método, a evolução do número e as limitações estão em
[eval/law_search/README.md](eval/law_search/README.md), e os resultados de cada pergunta
em [eval/law_search/RESULTADOS.md](eval/law_search/RESULTADOS.md). A origem do texto da
lei está em [data/law/README.md](data/law/README.md).

## Comandos

| Comando | O que faz |
| --- | --- |
| `just dev` | Sobe Postgres, backend e frontend com Docker |
| `just dev-backend` / `just dev-frontend` | Sobe cada parte localmente, com recarga automática |
| `just test` | Roda os testes do backend (pytest); os que precisam de PostgreSQL são pulados |
| `just lint` | Roda ruff, mypy, ESLint e o type-check do TypeScript |
| `just fmt` | Formata o código do backend |
| `just migrate` | Aplica as migrações do banco |
| `just analyze ARQUIVO.pdf ...` | Analisa um ou mais editais (campos e riscos) com o LLM real, sem banco (tem custo) |
| `just index-law` | Indexa a Lei 14.133 no PostgreSQL |
| `just eval-law` | Mede o recall@5 da busca na lei e gera o relatório |
| `just eval` | Avalia a extração contra o gabarito e gera `eval/RESULTADOS.md` (tem custo; `--reuse` refaz sem custo) |
| `just eval-check` | Confere o gabarito anotado, sem custo |

## Estrutura

```
backend/    API FastAPI, migrações Alembic e testes
frontend/   Interface Next.js
eval/       Gabarito, scripts e relatórios de avaliação
data/       Editais de exemplo e caches locais
docs/       Decisões de arquitetura e guias
```

## Segurança, governança e custos

O que o sistema faz com os dados, onde a decisão continua humana, os riscos de erro da IA e
como são reduzidos estão em [docs/GOVERNANCA.md](docs/GOVERNANCA.md). Em resumo:

- **Dados:** editais e lei são públicos; o sistema não precisa de dados de pessoas físicas.
- **Limite de gasto:** US$ 3,00 por análise e US$ 0,50 por verificação de aptidão
  (`ANALYSIS_MAX_COST_USD`, `ELIGIBILITY_MAX_COST_USD`). Uma chamada que pudesse passar do
  limite não é feita.
- **Rate limit por IP:** 120 requisições por minuto e 30 por hora nas rotas que custam
  dinheiro ou consultam o PNCP (resposta 429).
- **Upload:** só PDF, até 50 MB e 300 páginas, com o nome do arquivo limpo.
- **Auditoria:** `GET /analyses/ID/audit` mostra o documento (hash e origem), as versões e
  os hashes dos prompts, os modelos e cada chamada ao LLM com tokens e custo.

## Decisões de arquitetura

As decisões relevantes ficam registradas em [docs/DECISOES.md](docs/DECISOES.md), com
contexto, opções consideradas, escolha e trade-off.

## Aviso

Esta ferramenta é um apoio à leitura de editais e não substitui parecer jurídico.
