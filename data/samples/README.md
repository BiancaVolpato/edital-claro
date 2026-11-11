# Editais de exemplo

Editais reais e públicos, baixados do PNCP (Portal Nacional de Contratações Públicas) em
**11/11/2026** pela API oficial. São usados nos testes de ingestão.

Como os arquivos foram localizados:

1. Busca de contratações: `GET https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao`
   com `dataInicial=20261001`, `dataFinal=20261031`, `codigoModalidadeContratacao=4`
   (Concorrência - Eletrônica) e `uf=SC`.
2. Lista de arquivos de cada contratação:
   `GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos`.
3. Download do arquivo de tipo "Edital" pela URL informada na lista.

## Arquivos

### `florianopolis_cc_90330_2026.pdf`

| Campo | Valor |
| --- | --- |
| Órgão | Município de Florianópolis (CNPJ 82.892.282/0001-43) |
| Contratação | Concorrência nº 90330/2026, obras da macrodrenagem de Canasvieiras |
| Nº de controle PNCP | `82892282000143-1-000306/2026` |
| Arquivo no PNCP | documento 2, "CC 90330-2026 - macrodrenagem canasvieiras.pdf" |
| URL | <https://pncp.gov.br/pncp-api/v1/orgaos/82892282000143/compras/2026/306/arquivos/2> |
| Tamanho e páginas | 2,99 MB, 88 páginas, todas com texto nativo |
| SHA-256 | `cd74118447935b4345128e58e6e0f43e8f6dad19cfa8825a248b80f4be949091` |

Por que este: é o caso longo do critério de aceite (mais de 80 páginas) e traz problemas
típicos de PDFs gerados por editores online: caracteres invisíveis no meio do texto e
títulos de cláusula quebrados em duas linhas.

### `lauro_muller_cc_233_2026.pdf`

| Campo | Valor |
| --- | --- |
| Órgão | Município de Lauro Müller (CNPJ 82.558.909/0001-24) |
| Contratação | Concorrência nº 233/PMLM/2026, pavimentação da Rua Isaac Bertoncini |
| Nº de controle PNCP | `82558909000124-1-000290/2026` |
| Arquivo no PNCP | documento 1, "233__Concorrencia_Pavimentao_Rua_Isaac_Bertoncini" |
| URL | <https://pncp.gov.br/pncp-api/v1/orgaos/82558909000124/compras/2026/290/arquivos/1> |
| Tamanho e páginas | 0,24 MB, 28 páginas, todas com texto nativo |
| SHA-256 | `8e79641ee2d5f0ce24780b4f466dac43fab7b24deb1a89a45ed5187153260ef3` |

Por que este: edital curto de prefeitura pequena, com o número da página repetido no topo
de todas as páginas (caso de teste da remoção de cabeçalhos). A contratação tem também
uma retificação posterior (documento 2), que não foi usada.

### `lauro_muller_cc_233_2026_ocr_misto.pdf` (derivado)

**Não é um arquivo do PNCP.** Foi gerado por `build_ocr_sample.py` a partir das páginas
3 a 5 do edital de Lauro Müller: as páginas 3 e 5 foram copiadas como estão e a página 4
foi substituída por uma imagem dela mesma (200 dpi, tons de cinza), sem camada de texto.
Para um leitor de PDF, é o mesmo que uma página escaneada.

| Campo | Valor |
| --- | --- |
| Tamanho e páginas | 0,45 MB, 3 páginas (a do meio sem texto) |
| SHA-256 | `534ed0b7d7b18c556c9b7f608d9a857fbcc5156fb3c3cc2c677bb755d4ab19ae` |

Por que derivado: entre 18 arquivos de edital inspecionados, nenhum era escaneado por
inteiro, e a única página escaneada encontrada era uma ART com nome, CPF e assinatura de
uma pessoa, que não deve ir para um repositório público. O arquivo derivado ainda tem a
vantagem de ter gabarito: o texto original da página 4 permite medir o quanto o OCR
recupera.

Para gerar de novo, a partir da pasta `backend/`:

```bash
uv run python ../data/samples/build_ocr_sample.py
```

### Editais adicionados na Etapa 5

Mesma busca e mesma data de acesso (11/11/2026); todos de pavimentação, para ter cinco
editais de órgãos diferentes na verificação da análise de riscos.

| Arquivo | Órgão | Contratação | Nº de controle PNCP | Páginas | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `planalto_alegre_cce_63_2026.pdf` | Município de Planalto Alegre (CNPJ 95.990.255/0001-55) | Concorrência Eletrônica nº 63/2026, pavimentação com pedras irregulares | `95990255000155-1-000065/2026` | 58 | `a738205e82062be35cd637442f58450dd7af279696047d44cd9f2124dea4aac0` |
| `witmarsum_cce_4_2026.pdf` | Município de Witmarsum (CNPJ 83.102.442/0001-76) | Concorrência Eletrônica nº 4/2026, pavimentação asfáltica | `83102442000176-1-000156/2026` | 33 | `bff66886aa7958a0011431aa6668972f6131f90d977b47cf6b51d64d36f501ee` |
| `palhoca_cce_241_2026.pdf` | Município de Palhoça (CNPJ 82.892.316/0001-08) | Concorrência nº 241/2026, repavimentação com lajotas ou paver | `82892316000108-1-000324/2026` | 34 | `f46c88c576cca2131bc954fe2aff86f88d6de55fb23e9dfd5faafc56471b9989` |

URLs dos arquivos, todos o documento 1 da contratação:

- <https://pncp.gov.br/pncp-api/v1/orgaos/95990255000155/compras/2026/65/arquivos/1>
- <https://pncp.gov.br/pncp-api/v1/orgaos/83102442000176/compras/2026/156/arquivos/1>
- <https://pncp.gov.br/pncp-api/v1/orgaos/82892316000108/compras/2026/324/arquivos/1>

O de Palhoça revelou um defeito na extração de texto (ADR-026 em `docs/DECISOES.md`).

## Uso

Os editais são documentos públicos, publicados pelos próprios órgãos no PNCP. Estão aqui
apenas como material de teste.
