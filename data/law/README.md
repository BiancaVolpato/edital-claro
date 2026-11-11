# Lei 14.133/2021: texto oficial

Base de conhecimento usada para fundamentar os riscos apontados em um edital.

## Arquivos

| Arquivo | O que é |
| --- | --- |
| `L14133.html` | Página oficial da Lei nº 14.133, de 1º de abril de 2021, como publicada pelo Planalto (texto compilado) |
| `L14133.embeddings.npz` | Embeddings dos dispositivos da lei, calculados com `intfloat/multilingual-e5-base` |

## Fonte

| Campo | Valor |
| --- | --- |
| Fonte | Presidência da República, Subchefia para Assuntos Jurídicos (Planalto) |
| URL | <https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/L14133.htm> |
| Data de acesso | 11/11/2026 |
| SHA-256 do HTML | `f0d1ca8938941e581c8f482de6c6e53a73aa02756655b7eeda47658f33e08e0d` |
| Codificação | windows-1252 |

O arquivo foi salvo pelo navegador ("Salvar como", página da Web), porque o site do
Planalto recusa downloads automatizados. Para atualizar o texto, repita o procedimento,
salve por cima de `L14133.html` e rode a indexação: os embeddings dos dispositivos que
mudaram são recalculados e o cache é atualizado.

A página traz o texto compilado, isto é, com as alterações posteriores. O parser:

- descarta o texto riscado (redações superadas);
- quando um dispositivo aparece mais de uma vez (redação antiga seguida da nova, ou
  "(VETADO)" seguido do texto promulgado depois), fica com a última ocorrência;
- não indexa dispositivos vetados ou revogados;
- trata os artigos de outras leis citados entre aspas (como os do Código Penal
  incluídos pelo art. 178) como texto do artigo que os cita.

Resultado: 196 artigos (os 194 originais mais o 44-A e o 184-A) e 1.410 dispositivos
indexados (artigos, parágrafos, incisos e alíneas com conteúdo).

## Como indexar

Com o banco no ar e as migrações aplicadas, a partir da pasta `backend/`:

```bash
uv run python scripts/index_law.py
```

Leva cerca de 2 segundos, porque os embeddings vêm do cache. Sem o cache, o cálculo
leva de 5 a 8 minutos em CPU e baixa o modelo de embeddings (cerca de 1 GB).

## Uso

Leis são atos oficiais e seu texto é de domínio público. A pasta `L14133_files`, que o
navegador cria ao salvar a página, não é usada e está fora do controle de versão.
