# Guia de anotação do gabarito

O gabarito diz, para cada edital, qual é a resposta certa de cada campo. A avaliação
(`just eval`) compara a extração com ele. Um gabarito errado produz números errados, então
anote com calma e registre as dúvidas.

## Como começar um edital

1. Coloque o PDF em `data/samples/` (e registre a origem em `data/samples/README.md`).
2. Copie `eval/golden/_template.json` para `eval/golden/NOME_DO_ARQUIVO.json`, com o mesmo
   nome do PDF.
3. Preencha `document`. O SHA-256 garante que o gabarito é do arquivo certo:

   ```bash
   python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" data/samples/NOME.pdf
   ```

4. Leia o edital inteiro (corpo e anexos) e preencha `fields` e `requirements`.
5. Confira o arquivo:

   ```bash
   just eval-check
   ```

Há um exemplo completo em [golden/lauro_muller_cc_233_2026.json](golden/lauro_muller_cc_233_2026.json),
preparado com ajuda do assistente de código e ainda não revisado: revise-o antes de usar os
números.

## Regras gerais

- **Anote o que o edital diz, não o que deveria dizer.** Se o edital pede garantia de 10%
  e a lei permite 5%, anote 10%.
- **`null` quer dizer "o edital não informa".** Use quando a informação não está em lugar
  nenhum do PDF ou está ambígua demais para ter uma resposta certa. Explique em `notes`.
- **`pages`** lista as páginas (numeração do leitor de PDF, começando em 1) onde a
  informação aparece. Serve para medir se as citações apontam para o lugar certo. Liste
  todas as páginas onde ela aparece de forma clara; deixe `[]` quando o valor é `null`.
- **Conflito dentro do edital** (ex.: duas datas de abertura diferentes): anote o valor do
  corpo do edital e descreva o conflito em `notes`.
- Marque `"reviewed": true` só depois que uma segunda leitura confirmar o arquivo.

## Campos

| Campo | Formato | Como comparar |
| --- | --- | --- |
| `number` | texto, ex.: `"Concorrência Eletrônica nº 233/PMLM/2026"` | semelhança de texto, e os números precisam ser os mesmos |
| `modality` | `concorrencia`, `pregao`, `concurso`, `leilao`, `dialogo_competitivo`, `dispensa`, `inexigibilidade`, `outra` | exato |
| `agency` | texto, ex.: `"Município de Lauro Muller"` | semelhança de texto |
| `object` | uma frase com o essencial do objeto | semelhança de texto |
| `estimated_value` | número em reais, sem R$: `60296.85` | exato (diferença de até 1 centavo) |
| `judgment_criterion` | `menor_preco`, `maior_desconto`, `melhor_tecnica_ou_conteudo_artistico`, `tecnica_e_preco`, `maior_lance`, `maior_retorno_economico`, `outro` | exato |
| `execution_regime` | `empreitada_por_preco_unitario`, `empreitada_por_preco_global`, `empreitada_integral`, `contratacao_por_tarefa`, `contratacao_integrada`, `contratacao_semi_integrada`, `fornecimento_e_prestacao_de_servico_associado`, `outro` | exato |
| `publication_date` | `"AAAA-MM-DD"` | exato |
| `opening` | `{"date": "AAAA-MM-DD", "time": "HH:MM"}` (`time` pode ser `null`) | data e hora exatas |
| `impugnation_deadline`, `clarification_deadline` | `{"date": ..., "rule": ...}` | se houver data, data exata; senão, semelhança da regra com os mesmos números |
| `execution_period` | `{"amount": 60, "unit": "dias"}` (`dias`, `meses` ou `anos`) | exato |
| `bid_guarantee`, `contract_guarantee` | `{"required": true, "percent": 5.0}` (`percent` pode ser `null`) | `required` e `percent` exatos |
| `site_visit` | `obrigatoria`, `facultativa`, `nao_exigida` | exato |
| `consortium_allowed`, `me_epp_exclusive` | `true` ou `false` | exato |

Dicas por campo:

- **`object`:** escreva o objeto sem o "contratação de empresa especializada para".
  A comparação tolera diferenças de redação, mas não de conteúdo.
- **`estimated_value`:** o valor total estimado ou máximo da contratação. Se o orçamento for
  sigiloso, `null`.
- **`publication_date`:** a data de publicação; se o edital só tiver a data de assinatura
  (ex.: "Lauro Muller, 01 de outubro de 2026"), use essa.
- **`opening`:** a sessão pública de abertura, não o fim do cadastro de propostas.
- **Prazos (`*_deadline`):** quando o edital dá uma regra ("até 3 dias úteis antes da
  abertura"), anote a regra em `rule` e deixe `date` nulo. Só preencha `date` se o edital
  escrever a data.
- **`execution_period`:** o prazo para executar a obra, não a vigência do contrato.
- **Garantias:** "não será exigida" é `{"required": false, "percent": null}`. Se o edital não
  falar do assunto, `null`.
- **`site_visit`:** `nao_exigida` quando o edital diz que não há visita ou não fala dela
  e não pede declaração; `facultativa` quando a visita é opcional (mesmo que peça
  declaração de quem não visitou).
- **`consortium_allowed`:** `null` se o edital não tratar de consórcio.

## Exigências de habilitação e anexos

Em `requirements`, cada lista tem uma exigência por item, com redação próxima à do edital:

- **Um item para cada documento ou condição**, seguindo as letras do edital (a, b, c...).
  Subitens que criam uma exigência nova (ex.: "c.1) Se ILG < 1, patrimônio líquido de 10%")
  viram um item à parte; subitens que só explicam o anterior, não.
- **Não junte itens diferentes** num só, nem divida um item em vários.
- Coloque cada exigência na seção em que o edital a coloca (jurídica, fiscal/social/
  trabalhista, técnica, econômico-financeira). Se o edital remete a outro documento
  ("conforme Termo de Referência"), anote a remissão como item.
- **Anexos:** um item por anexo, no formato `"Anexo I - Título"`, incluindo anexos sem número.

A avaliação compara cada item extraído com os do gabarito por semelhança de texto e conta
precisão (itens extraídos que estão no gabarito) e recall (itens do gabarito que foram
extraídos).

## Quantos editais

Para números que digam algo, anote de 15 a 20 editais de órgãos diferentes, com tamanhos
variados (de 20 a mais de 80 páginas) e pelo menos um com páginas escaneadas.
