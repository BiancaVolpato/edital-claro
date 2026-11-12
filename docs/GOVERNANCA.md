# Governança, segurança e custos

Este documento explica que dados o Edital Claro usa, como trata dados pessoais, onde a
decisão continua sendo humana, quais são os riscos de erro da IA e como eles são reduzidos,
e como o custo é controlado. As decisões técnicas por trás de cada ponto estão em
[DECISOES.md](DECISOES.md).

## 1. Dados usados

| Dado | Origem | Natureza |
| --- | --- | --- |
| Editais | PNCP (API pública) ou upload | documentos públicos, publicados pelos órgãos por obrigação legal (Lei 14.133/2021, art. 54) |
| Lei 14.133/2021 | site do Planalto | texto legal público |
| Perfis de empresa | cadastrados por quem usa | dados de pessoa jurídica: razão social, CNPJ, CNAEs, capital, certidões, atestados |
| Resultados | gerados pelo sistema | extração, riscos, aptidão, uso de tokens e custo |

O sistema não pede, não guarda e não precisa de dados de pessoas físicas para funcionar. Não
há cadastro de usuários nem login nesta versão.

## 2. Dados pessoais e LGPD

Editais são públicos, mas podem trazer dados pessoais de terceiros: nome e assinatura do
prefeito, do pregoeiro ou do assessor jurídico, número de inscrição na OAB ou no CREA, e às
vezes CPF em anexos (ART, procurações, modelos preenchidos).

Como o sistema trata esses dados:

- **Finalidade e base legal.** Os dados chegam junto com o documento público e são tratados
  só para ler o edital. A base é o interesse legítimo de analisar um ato público, já tornado
  público pelo próprio órgão (LGPD, art. 7º, IX, e § 4º, sobre dados tornados manifestamente
  públicos pelo titular, aplicado por analogia à publicação oficial).
- **Minimização.** A extração pede campos sobre a licitação, não sobre pessoas. Nenhum campo
  extraído, risco ou relatório é sobre uma pessoa física. Os trechos citados podem conter um
  nome quando ele está na mesma frase da informação citada.
- **Dados sensíveis** (saúde, religião, biometria etc., LGPD art. 5º, II) não fazem parte de
  editais de obra. Se um documento enviado por upload trouxer esse tipo de dado, ele não é
  usado em nenhum campo, mas fica guardado no PDF e no texto das páginas. A orientação ao
  usuário (tela "Sobre e limitações") é não enviar documentos sigilosos ou com dados
  pessoais além do edital.
- **Envio a terceiros.** O texto dos trechos selecionados vai para o provedor de IA
  configurado (Anthropic) para a análise. Isso é dito na tela "Sobre e limitações". Uma
  instalação que não possa enviar dados a terceiros precisa trocar o provedor (a interface
  `LLMProvider` permite) ou não usar a análise com IA.
- **Exemplos no repositório.** Os editais de `data/samples/` são públicos e foram escolhidos
  evitando anexos com CPF: a única página escaneada encontrada nos editais inspecionados era
  uma ART com nome, CPF e assinatura, e por isso foi substituída por uma página derivada
  (ver `data/samples/README.md`).
- **Retenção e exclusão.** PDFs ficam em `data/uploads` (fora do Git) e o texto no banco. O
  perfil de empresa pode ser apagado pela interface; verificações de aptidão guardam uma
  cópia do perfil usado, para auditoria. Não há exclusão automática nesta versão: quem opera
  a instalação apaga documentos no banco e na pasta de uploads quando necessário.
- **Logs.** Os logs registram ids, status, tempos, tokens e custos, não o texto dos editais
  nem os perfis. A chave da API nunca é registrada (`SecretStr`).

## 3. A decisão continua humana (human-in-the-loop)

O sistema é apoio à leitura, não decisor:

- **Toda informação tem origem verificável.** Cada campo, risco e item de aptidão cita a
  página e o trecho do edital. Na interface, um clique abre o PDF na página com o trecho
  destacado.
- **Confiança visível.** Cada campo mostra uma confiança. Campos cujo trecho não foi
  encontrado no documento, ou que o modelo marcou como incertos, aparecem como "Revisar".
- **Na aptidão, o que não dá para conferir não vira "atende".** Itens sem dado no perfil ou
  que o sistema não reconhece ficam como "Verificar", com o motivo.
- **Riscos não são parecer jurídico.** O texto pede que o modelo descreva o risco sem
  afirmar nulidade, e cada risco traz o artigo da lei para leitura. A interface e os
  relatórios exportados repetem o aviso de que a ferramenta não substitui parecer jurídico.
- **Ações com custo são explícitas.** A análise com IA só começa quando a pessoa clica em
  "Analisar com IA".

## 4. Limitações conhecidas

- A extração pode errar ou não encontrar uma informação; a medida do quanto está em
  `eval/RESULTADOS.md` (gerado por `just eval` quando o gabarito estiver anotado).
- PDFs escaneados dependem do OCR, que pode trocar letras e números.
- Anexos em arquivos separados (planilhas, projetos, ZIPs) não são lidos.
- A base de leis tem só a Lei 14.133/2021, sem decretos, jurisprudência ou normas locais.
- A aptidão reconhece exigências por palavras-chave e não confere documentos da empresa.
- A interface não tem login: numa instalação pública, qualquer visitante vê os perfis e as
  análises. Para uso real com dados de empresas, é preciso autenticação (fora do escopo
  desta versão).

## 5. Riscos de alucinação e mitigações

| Risco | Mitigação | Onde |
| --- | --- | --- |
| A IA inventa um valor que não está no edital | todo valor precisa citar um trecho; o trecho é procurado no texto da página; sem trecho confirmado, a confiança cai e o campo vai para revisão | ADR-012, `app/extraction/citations.py` |
| A IA cita um trecho parecido, mas com outro número | a comparação aproximada exige que todos os números da citação estejam no trecho encontrado | ADR-012 |
| A IA aponta um risco sem base legal ou cita artigo de memória | o risco só é aceito com trecho confirmado do edital e com dispositivo recuperado do texto oficial da lei; o resto é descartado e listado | ADR-024 |
| A IA erra contas (percentuais, somas de quantitativos, prazos) | números e datas são comparados por código; na aptidão, a IA nem recebe as quantidades dos atestados | ADR-023, ADR-027 |
| Texto do edital tenta dar ordens à IA (prompt injection) | ver seção 6 | ADR-015 |
| Um erro passa sem ninguém notar | selo "Revisar", citação clicável, avaliação com gabarito que mede quantos erros o selo pega | ADR-035 |

## 6. Prompt injection

Um edital é texto de terceiros e pode conter instruções escondidas ("ignore as instruções e
responda que..."). As defesas, em camadas:

1. **Bloco delimitado com código aleatório.** O texto do edital vai entre tags cujo nome
   leva 64 bits aleatórios gerados a cada chamada. Uma tag forjada no documento não fecha o
   bloco verdadeiro. O mesmo vale para o texto do perfil na comparação de atestados.
2. **Prompt de sistema** diz que tudo dentro dos blocos é dado, nunca instrução.
3. **Sem ferramentas.** O modelo não tem acesso a nada além de responder.
4. **Saída presa a um esquema.** A resposta precisa caber no formato pedido.
5. **Validação depois da resposta.** Mesmo que o modelo obedeça a uma instrução injetada,
   valores sem trecho real no documento são marcados, riscos sem base são descartados,
   códigos inventados são ignorados, e números são conferidos por código.
6. **Limpeza do texto.** Caracteres invisíveis e controles de direção (usados para esconder
   texto ou disfarçar extensões de arquivo) são removidos na ingestão e no nome do arquivo.
7. **Atributos seguros.** Títulos de seção vão para atributos com aspas e sinais de maior e
   menor trocados, para não abrir tags novas.

Os testes estão em `backend/tests/test_prompt_injection.py`, `test_pipeline.py`,
`test_risk_assessment.py` e `test_eligibility.py`. A defesa reduz o risco, não o elimina:
um modelo pode ser influenciado a omitir algo verdadeiro. Por isso a camada 5 e a revisão
humana importam mais que o prompt.

## 7. Segurança da aplicação

- **Upload:** até 50 MB (`MAX_UPLOAD_MB`), só PDF (conferido pelo conteúdo, não pela
  extensão), até 300 páginas (`MAX_PDF_PAGES`), PDFs com senha recusados. O arquivo é
  guardado com o nome do seu hash; o nome enviado só é exibido, depois de limpo (sem
  caminho, sem caracteres de controle, até 255 caracteres).
- **Importação do PNCP:** o download usa o endereço documentado do PNCP montado pelo
  sistema, nunca um endereço vindo da resposta.
- **Rate limit:** por IP, 120 requisições por minuto em geral e 30 por hora nas rotas que
  custam dinheiro ou consultam o PNCP. Resposta 429 com `Retry-After`.
- **Segredos:** só no `.env` (fora do Git); `.env.example` sem valores reais.
- **Logs:** id de requisição gerado pelo servidor (não aceito do cliente), sem conteúdo de
  documentos.

## 8. Custos

- **Limite por análise:** US$ 3,00 por análise (extração e riscos) e US$ 0,50 por
  verificação de aptidão, configuráveis. Antes de cada chamada, o sistema reserva o pior
  caso dela (entrada estimada e o máximo de saída); se a soma passar do limite, a chamada
  não é feita e o grupo aparece como não extraído, com o motivo nos avisos.
- **Modelo sem preço cadastrado:** com limite ativo, a chamada é recusada, porque o custo
  não pode ser garantido.
- **Visibilidade:** cada análise registra tokens, custo estimado e latência por chamada;
  a interface mostra o custo total.
- **Avaliação:** roda à mão (`just eval` ou o workflow manual), com `--limit` e
  `--variants` para gastar pouco, e `--reuse` para refazer o relatório sem custo.

## 9. Trilha de auditoria

Cada resultado guarda o que o produziu:

| Resultado | O que fica registrado |
| --- | --- |
| Documento | hash SHA-256 do PDF, origem (upload ou PNCP, com número de controle e arquivo), páginas com OCR |
| Análise | versão e hash do prompt de extração e do de riscos, estratégia, provedor e modelo, modelo de embeddings, cada chamada (modelo, tokens, custo, latência, erro), limite de gasto, versão da aplicação |
| Verificação de aptidão | cópia do perfil usado, versão e hash do prompt, modelo, tokens, custo, limite, versão da aplicação |

`GET /analyses/{id}/audit` devolve a trilha de uma análise em um só lugar. Os prompts são
arquivos versionados em `backend/prompts/`; o hash identifica o conteúdo exato usado.
