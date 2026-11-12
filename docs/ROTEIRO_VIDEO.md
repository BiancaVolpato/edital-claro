# Roteiro do vídeo (3 minutos)

Vídeo de apresentação do Edital Claro para o programa de trainee em IA. Quatro blocos: o
problema (30 s), a demonstração (90 s), avaliação e decisões (40 s) e próximos passos
(20 s). A fala tem cerca de 400 palavras, num ritmo confortável de 140 palavras por minuto.

**Antes de gravar**

- Abra a demonstração e espere ela carregar: o servidor gratuito leva cerca de 1 minuto
  para acordar.
- Deixe abertas três abas: a página inicial, a análise de Witmarsum e o
  [README](../README.md) na seção "Resultados da avaliação".
- Os números entre colchetes, `[assim]`, só podem ser ditos depois de medidos. Troque
  pelos valores de `eval/RESULTADOS.md` quando o gabarito estiver anotado, ou use a fala
  alternativa indicada.

---

## 1. O problema (0:00 a 0:30)

**Tela:** o PDF do edital de Witmarsum aberto, rolando rápido pelas 33 páginas. Depois, a
página da qualificação técnica, com "3.404 m²" em destaque.

**Fala:**

> Uma construtora pequena que quer disputar uma obra pública precisa ler editais como
> este: 33 páginas de linguagem jurídica, e cada prefeitura escreve de um jeito. Neste,
> a empresa precisa de atestados que somem 3.404 metros quadrados de pavimentação, de
> patrimônio de 10% do valor da obra e de todas as certidões válidas no dia da sessão. Uma
> certidão vencida cinco dias antes já desclassifica. O Edital Claro lê o edital e aponta
> isso, sempre mostrando de onde tirou cada informação.

## 2. Demonstração (0:30 a 2:00)

**0:30 a 0:45. Tela:** a página inicial da demo, com a lista de análises e a busca no PNCP.

> Os editais vêm do Portal Nacional de Contratações Públicas, por busca, ou por upload.
> Na demonstração, três já estão analisados, para não gastar com a IA.

**0:45 a 1:15. Tela:** abra a análise de Witmarsum, aba Campos. Clique na citação do valor
estimado: o PDF abre na página com o trecho destacado.

> A IA extrai 22 informações: valor, datas, garantias, exigências de habilitação. Cada uma
> cita a página e o trecho literal. Um clique abre o PDF e destaca o trecho. E o sistema
> confere sozinho se esse trecho existe mesmo na página: o que não for confirmado aparece
> como "Revisar". É a principal defesa contra alucinação.

**1:15 a 1:35. Tela:** aba Riscos. Aponte, num risco, o trecho do edital e o artigo da lei citados.

> Os riscos vêm de duas camadas. O que a Lei 14.133 define em números, como prazos e
> limites de garantia, é conferido por regras. O que exige interpretação fica com a IA,
> mas só vale se citar o trecho do edital e um artigo recuperado do texto oficial da lei.

**1:35 a 2:00. Tela:** clique em "Verificar aptidão". A tela abre com a verificação salva do
perfil de exemplo, feita com a IA. Mostre o veredito, o que falta e os prazos críticos.

> Por fim, a aptidão. Eu cadastro o perfil da empresa, e o sistema compara exigência por
> exigência. As contas, como somar atestados e comparar datas, são feitas por código. A IA
> só responde se um atestado é do mesmo tipo de serviço. O resultado diz o que atende, o
> que não atende e o que ainda precisa ser verificado, com o prazo de cada certidão.

## 3. Avaliação e decisões (2:00 a 2:40)

**Tela:** o README, seção "Resultados da avaliação". Depois, `docs/DECISOES.md` rolando.

> Para saber se funciona, eu medi. A busca na lei acerta o artigo certo entre os cinco
> primeiros em 9 de 10 perguntas. A extração é comparada campo a campo com um gabarito
> anotado à mão: `[X]`% de acerto, `[Y]`% de alucinação, e o selo "Revisar" pega `[Z]`% dos
> erros. A mesma avaliação compara modelos, e o mais barato que fica perto do melhor é o
> escolhido. Cada escolha está registrada com as alternativas e o trade-off, e a análise
> tem limite de gasto, rate limit e trilha de auditoria.

**Fala alternativa,** enquanto o gabarito não estiver anotado (troque a segunda e a
terceira frases):

> A extração tem um avaliador pronto, que compara cada campo com um gabarito anotado à mão
> e mede quantos erros o selo "Revisar" pega. O próximo passo é completar esse gabarito.

## 4. Próximos passos (2:40 a 3:00)

**Tela:** o README, seção "Limitações e próximos passos".

> Os próximos passos são completar o gabarito, ler os anexos com as planilhas de
> quantitativos e incluir a jurisprudência do TCU. A ideia é que nenhuma empresa perca uma
> licitação por não ter achado uma exigência na página 27. Obrigada!

---

## Checklist de gravação

- [ ] Resolução de 1920×1080 e zoom do navegador em 110% para o texto ficar legível.
- [ ] Sem notificações na tela, e nenhuma aba com dados pessoais.
- [ ] Ensaie com cronômetro: cada bloco precisa caber no tempo dele.
- [ ] Legendas: o texto das falas acima serve de base.
