import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sobre e limitações · Edital Claro" };

export default function AboutPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 py-10">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Sobre o Edital Claro</h1>
        <p className="text-muted-foreground">
          Uma ferramenta de apoio à leitura de editais de obras públicas. Ela não substitui
          parecer jurídico nem a leitura do edital completo.
        </p>
      </header>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">O que a ferramenta faz</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            Lê o edital (PDF enviado ou importado do PNCP) e extrai 22 informações: identificação,
            datas, garantias, participação, exigências de habilitação e anexos.
          </li>
          <li>
            Cada informação cita a página e o trecho literal do edital. O sistema confere se o
            trecho existe na página indicada; o que não for confirmado aparece marcado para revisão.
          </li>
          <li>
            Aponta riscos de duas formas: regras automáticas para o que a Lei 14.133/2021 define em
            números ou datas, e IA para o que exige interpretação, sempre com o trecho do edital e
            o artigo da lei recuperado do texto oficial.
          </li>
          <li>
            Compara o edital com o perfil de uma empresa e diz, exigência por exigência, o que
            atende, o que não atende e o que precisa ser conferido à mão.
          </li>
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">O que a ferramenta não faz</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>Não dá parecer jurídico e não diz se uma cláusula é ilegal ou se uma impugnação será aceita.</li>
          <li>
            Não lê planilhas orçamentárias, projetos e anexos enviados em arquivos separados; só o
            PDF analisado.
          </li>
          <li>
            Não abre arquivos ZIP do PNCP: nesses casos, baixe o arquivo e envie os PDFs pelo
            upload.
          </li>
          <li>
            Não confere documentos da empresa (balanço, contrato social, certidões): usa o que foi
            informado no perfil.
          </li>
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Limitações conhecidas</h2>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            A IA pode errar ou deixar de encontrar uma informação. A confiança mostrada em cada
            campo cai quando a citação não é confirmada; campos marcados com “Revisar” pedem
            conferência humana.
          </li>
          <li>
            PDFs escaneados passam por OCR, que pode trocar letras e números. Confira os valores
            nesses casos.
          </li>
          <li>
            A comparação de aptidão reconhece as exigências por palavras-chave. O que ela não
            reconhece fica como “Verificar”, nunca como “Atende”.
          </li>
          <li>
            A base de leis contém apenas a Lei 14.133/2021, sem decretos, jurisprudência ou normas
            locais.
          </li>
        </ul>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Dados e privacidade</h2>
        <p>
          O texto do edital é enviado ao provedor de IA configurado no servidor para a análise. Não
          envie documentos sigilosos. As marcações do checklist ficam só no seu navegador.
        </p>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Demonstração pública</h2>
        <p>
          Na demonstração, três editais de exemplo já foram analisados pela IA, com o pipeline
          real, e os resultados ficam guardados para você ver sem espera e sem custo. Por isso
          envio de PDF, importação do PNCP e novas análises ficam desativados. Perfis e
          verificações de aptidão funcionam, mas sem a etapa de IA (a comparação de atestados
          fica como “Verificar”). Não há login: não cadastre dados reais de empresas. Os dados
          criados por visitantes são apagados quando a demonstração é restaurada.
        </p>
      </section>
    </main>
  );
}
