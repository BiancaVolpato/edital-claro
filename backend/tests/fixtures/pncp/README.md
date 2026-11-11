# Respostas gravadas do PNCP

Respostas reais das APIs públicas do PNCP, gravadas em **11/11/2026** e usadas pelos testes
em `tests/test_pncp.py`, para que nenhum teste dependa da rede.

| Arquivo | Requisição |
| --- | --- |
| `publicacao_20261104_sc_mod4_p{1,2,3}.json` | `GET /api/consulta/v1/contratacoes/publicacao?dataInicial=20261104&dataFinal=20261104&codigoModalidadeContratacao=4&uf=SC&pagina=N&tamanhoPagina=10` |
| `publicacao_20261104_sc_mod5_p1.json` | o mesmo, com `codigoModalidadeContratacao=5` |
| `compra_82939422000191_2026_153.json` | `GET /api/consulta/v1/orgaos/82939422000191/compras/2026/153` |
| `arquivos_82939422000191_2026_153.json` | `GET /api/pncp/v1/orgaos/82939422000191/compras/2026/153/arquivos` |

As buscas foram gravadas com 10 resultados por página, para que haja mais de uma página. O
cliente pede 50 por página; nos testes, o servidor falso escolhe o arquivo pela data, UF,
modalidade e página, sem olhar o tamanho da página.

O download do edital não está gravado: nos testes, o servidor falso devolve um PDF de
`data/samples/` no lugar do arquivo real.
