# Snapshots da demonstração

Cada arquivo `<edital>.json` aqui é uma análise feita pelo pipeline real, com a IA real,
sobre um PDF de `data/samples/`: campos extraídos com citações, riscos, uso de tokens e custo
por chamada, versões e hashes dos prompts, e a verificação de aptidão do perfil de exemplo
(`data/profiles/construtora_exemplo.json`).

O servidor em modo demonstração (`DEMO_MODE=true`) carrega esses arquivos no banco ao
subir. O PDF não é copiado: o snapshot aponta o arquivo em `data/samples/` e o SHA-256 dele,
e o seed roda a ingestão normal. Detalhes na ADR-039 e em `docs/DEPLOY.md`.

| Comando | O que faz |
| --- | --- |
| `just demo-generate` | analisa os três editais da demo com a IA (custa dinheiro) e grava os snapshots |
| `just demo-seed` | carrega no banco os snapshots que ainda não estão lá |
| `just demo-reset` | apaga documentos, análises e perfis do banco e semeia de novo |
| `just demo-export <id> <nome>` | grava uma análise do banco como `<nome>.json` |

Não edite os JSON à mão: eles são o registro do que a IA respondeu.
