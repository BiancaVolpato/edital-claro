# Busca na Lei 14.133/2021: resultados

Gerado por `backend/scripts/eval_law_search.py` em 11/11/2026.

- Dispositivos indexados: 1410
- Modelo de embeddings: `intfloat/multilingual-e5-base`
- Perguntas: 10 (em `questions.json`)
- Métrica: recall@5, a fração das perguntas em que um dispositivo do artigo esperado aparece entre os 5 primeiros resultados
- Meta: recall@5 de pelo menos 0,8

## Resumo por modo de busca

| Modo | Recall@5 | Acertos | MRR |
| --- | --- | --- | --- |
| Híbrida | 0,90 | 9/10 | 0,90 |
| Só vetorial | 0,90 | 9/10 | 0,82 |
| Só texto (full-text) | 0,60 | 6/10 | 0,46 |

MRR (mean reciprocal rank) é a média de 1/posição do artigo esperado: 1,00 significa que ele veio sempre em primeiro lugar.

## Posição do artigo esperado, por pergunta

| Pergunta | Artigo esperado | Híbrida | Só vetorial | Só texto |
| --- | --- | --- | --- | --- |
| Até quando posso impugnar o edital ou pedir esclarecimentos? | Art. 164 | 1 | 1 | 1 |
| Qual é o percentual máximo da garantia de execução do contrato em uma obra? | Art. 98 | 1 | 1 | fora |
| O órgão pode pedir garantia de proposta maior que 1% do valor estimado? | Art. 58 | 1 | 1 | 1 |
| Quantos dias no mínimo deve haver entre a divulgação do edital e a apresentação das propostas em uma obra? | Art. 55 | 1 | 1 | 4 |
| O edital pode exigir atestado de capacidade técnica com quantidade mínima acima de metade do que será contratado? | Art. 67 | 1 | 1 | 1 |
| Que índices contábeis e documentos podem ser exigidos para comprovar a saúde financeira da empresa? | Art. 69 | 1 | 1 | 1 |
| Empresas podem se juntar em consórcio para participar da licitação? | Art. 15 | 1 | 1 | 3 |
| Quais são as formas de escolher a proposta vencedora? | Art. 33 | fora | fora | fora |
| Quais modalidades de licitação existem? | Art. 28 | 1 | 1 | fora |
| A prefeitura pode obrigar a empresa a visitar o local da obra antes de participar? | Art. 63 | 1 | 4 | fora |

## Resultados da busca híbrida

**Até quando posso impugnar o edital ou pedir esclarecimentos?** (esperado: Art. 164)

1. `Art. 164, parágrafo único` ✔: A resposta à impugnação ou ao pedido de esclarecimento será divulgada em sítio eletrônico oficial no prazo de até 3 (três) dias úteis, limitado ao último dia út...
2. `Art. 164` ✔: Qualquer pessoa é parte legítima para impugnar edital de licitação por irregularidade na aplicação desta Lei ou para solicitar esclarecimento sobre os seus term...
3. `Art. 168, parágrafo único`: Na elaboração de suas decisões, a autoridade competente será auxiliada pelo órgão de assessoramento jurídico, que deverá dirimir dúvidas e subsidiá-la com as in...
4. `Art. 102, I, d`: requerer esclarecimentos ao responsável técnico pela obra ou pelo fornecimento;
5. `Art. 96, § 3º`: O edital fixará prazo mínimo de 1 (um) mês, contado da data de homologação da licitação e anterior à assinatura do contrato, para a prestação da garantia pelo c...

**Qual é o percentual máximo da garantia de execução do contrato em uma obra?** (esperado: Art. 98)

1. `Art. 98, parágrafo único` ✔: Nas contratações de serviços e fornecimentos contínuos com vigência superior a 1 (um) ano, assim como nas subsequentes prorrogações, será utilizado o valor anua...
2. `Art. 98` ✔: Nas contratações de obras, serviços e fornecimentos, a garantia poderá ser de até 5% (cinco por cento) do valor inicial do contrato, autorizada a majoração dess...
3. `Art. 99`: Nas contratações de obras e serviços de engenharia de grande vulto, poderá ser exigida a prestação de garantia, na modalidade seguro-garantia, com cláusula de r...
4. `Art. 102, I, d`: requerer esclarecimentos ao responsável técnico pela obra ou pelo fornecimento;
5. `Art. 115, § 1º`: É proibido à Administração retardar imotivadamente a execução de obra ou serviço, ou de suas parcelas, inclusive na hipótese de posse do respectivo chefe do Pod...

**O órgão pode pedir garantia de proposta maior que 1% do valor estimado?** (esperado: Art. 58)

1. `Art. 58, § 1º` ✔: A garantia de proposta não poderá ser superior a 1% (um por cento) do valor estimado para a contratação.
2. `Art. 98, parágrafo único`: Nas contratações de serviços e fornecimentos contínuos com vigência superior a 1 (um) ano, assim como nas subsequentes prorrogações, será utilizado o valor anua...
3. `Art. 58, § 3º` ✔: Implicará execução do valor integral da garantia de proposta a recusa em assinar o contrato ou a não apresentação dos documentos para a contratação.
4. `Art. 96, § 3º`: O edital fixará prazo mínimo de 1 (um) mês, contado da data de homologação da licitação e anterior à assinatura do contrato, para a prestação da garantia pelo c...
5. `Art. 24, parágrafo único`: Na hipótese de licitação em que for adotado o critério de julgamento por maior desconto, o preço estimado ou o máximo aceitável constará do edital da licitação.

**Quantos dias no mínimo deve haver entre a divulgação do edital e a apresentação das propostas em uma obra?** (esperado: Art. 55)

1. `Art. 55, II, d` ✔: 35 (trinta e cinco) dias úteis, quando o regime de execução for o de contratação semi-integrada ou nas hipóteses não abrangidas pelas alíneas “a”, “b” e “c” des...
2. `Art. 55, I, b` ✔: 15 (quinze) dias úteis, nas hipóteses não abrangidas pela alínea “a” deste inciso;
3. `Art. 58, § 2º`: A garantia de proposta será devolvida aos licitantes no prazo de 10 (dez) dias úteis, contado da assinatura do contrato ou da data em que for declarada fracassa...
4. `Art. 164, parágrafo único`: A resposta à impugnação ou ao pedido de esclarecimento será divulgada em sítio eletrônico oficial no prazo de até 3 (três) dias úteis, limitado ao último dia út...
5. `Art. 25, § 8º, I`: reajustamento em sentido estrito, quando não houver regime de dedicação exclusiva de mão de obra ou predominância de mão de obra, mediante previsão de índices e...

**O edital pode exigir atestado de capacidade técnica com quantidade mínima acima de metade do que será contratado?** (esperado: Art. 67)

1. `Art. 67, § 2º` ✔: Observado o disposto no caput e no § 1º deste artigo, será admitida a exigência de atestados com quantidades mínimas de até 50% (cinquenta por cento) das parcel...
2. `Art. 67, § 5º` ✔: Em se tratando de serviços contínuos, o edital poderá exigir certidão ou atestado que demonstre que o licitante tenha executado serviços similares ao objeto da ...
3. `Art. 25, § 9º`: O edital poderá, na forma disposta em regulamento, exigir que percentual mínimo da mão de obra responsável pela execução do objeto da contratação seja constituí...
4. `Art. 25, § 9º, I`: mulheres vítimas de violência doméstica;
5. `Art. 122, § 1º`: O contratado apresentará à Administração documentação que comprove a capacidade técnica do subcontratado, que será avaliada e juntada aos autos do processo corr...

**Que índices contábeis e documentos podem ser exigidos para comprovar a saúde financeira da empresa?** (esperado: Art. 69)

1. `Art. 69, § 1º` ✔: A critério da Administração, poderá ser exigida declaração, assinada por profissional habilitado da área contábil, que ateste o atendimento pelo licitante dos í...
2. `Art. 69, I` ✔: balanço patrimonial, demonstração de resultado de exercício e demais demonstrações contábeis dos 2 (dois) últimos exercícios sociais;
3. `Art. 65, § 1º`: As empresas criadas no exercício financeiro da licitação deverão atender a todas as exigências da habilitação e ficarão autorizadas a substituir os demonstrativ...
4. `Art. 58, § 3º`: Implicará execução do valor integral da garantia de proposta a recusa em assinar o contrato ou a não apresentação dos documentos para a contratação.
5. `Art. 58, § 1º`: A garantia de proposta não poderá ser superior a 1% (um por cento) do valor estimado para a contratação.

**Empresas podem se juntar em consórcio para participar da licitação?** (esperado: Art. 15)

1. `Art. 15, § 4º` ✔: Desde que haja justificativa técnica aprovada pela autoridade competente, o edital de licitação poderá estabelecer limite máximo para o número de empresas conso...
2. `Art. 15, IV` ✔: impedimento de a empresa consorciada participar, na mesma licitação, de mais de um consórcio ou de forma isolada;
3. `Art. 14, II`: empresa, isoladamente ou em consórcio, responsável pela elaboração do projeto básico ou do projeto executivo, ou empresa da qual o autor do projeto seja dirigen...
4. `Art. 6º, IX`: licitante: pessoa física ou jurídica, ou consórcio de pessoas jurídicas, que participa ou manifesta a intenção de participar de processo licitatório, sendo-lhe ...
5. `Art. 49, I`: o objeto da contratação puder ser executado de forma concorrente e simultânea por mais de um contratado; e

**Quais são as formas de escolher a proposta vencedora?** (esperado: Art. 33)

1. `Art. 36, § 1º, IV`: obras e serviços especiais de engenharia;
2. `Art. 35, parágrafo único`: O critério de julgamento de que trata o caput deste artigo poderá ser utilizado para a contratação de projetos e trabalhos de natureza técnica, científica ou ar...
3. `Art. 36, § 1º`: O critério de julgamento de que trata o caput deste artigo será escolhido quando estudo técnico preliminar demonstrar que a avaliação e a ponderação da qualidad...
4. `Art. 56, § 5º`: Nas licitações de obras ou serviços de engenharia, após o julgamento, o licitante vencedor deverá reelaborar e apresentar à Administração, por meio eletrônico, ...
5. `Art. 35`: O julgamento por melhor técnica ou conteúdo artístico considerará exclusivamente as propostas técnicas ou artísticas apresentadas pelos licitantes, e o edital d...

**Quais modalidades de licitação existem?** (esperado: Art. 28)

1. `Art. 28` ✔: São modalidades de licitação:
2. `Art. 28, II` ✔: concorrência;
3. `Art. 8º, § 5º`: Em licitação na modalidade pregão, o agente responsável pela condução do certame será designado pregoeiro.
4. `Art. 31, § 4º`: O leilão não exigirá registro cadastral prévio, não terá fase de habilitação e deverá ser homologado assim que concluída a fase de lances, superada a fase recur...
5. `Art. 20`: Os itens de consumo adquiridos para suprir as demandas das estruturas da Administração Pública deverão ser de qualidade comum, não superior à necessária para cu...

**A prefeitura pode obrigar a empresa a visitar o local da obra antes de participar?** (esperado: Art. 63)

1. `Art. 63, § 2º` ✔: Quando a avaliação prévia do local de execução for imprescindível para o conhecimento pleno das condições e peculiaridades do objeto a ser contratado, o edital ...
2. `Art. 115, § 6º`: Nas contratações de obras, verificada a ocorrência do disposto no § 5º deste artigo por mais de 1 (um) mês, a Administração deverá divulgar, em sítio eletrônico...
3. `Art. 102, I, d`: requerer esclarecimentos ao responsável técnico pela obra ou pelo fornecimento;
4. `Art. 115, § 4º`: Nas contratações de obras e serviços de engenharia, sempre que a responsabilidade pelo licenciamento ambiental for da Administração, a manifestação prévia ou li...
5. `Art. 118`: O contratado deverá manter preposto aceito pela Administração no local da obra ou do serviço para representá-lo na execução do contrato.
