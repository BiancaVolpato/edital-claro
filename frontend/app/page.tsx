import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PncpSearch } from "@/components/pncp-search";
import { RecentAnalyses } from "@/components/recent-analyses";
import { UploadCard } from "@/components/upload-card";
import { getBackendHealth } from "@/lib/api";

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-10">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Entenda um edital de obra pública em minutos
        </h1>
        <p className="max-w-3xl text-muted-foreground">
          O Edital Claro lê o edital com IA e mostra os dados principais, o checklist de
          habilitação e os riscos à luz da Lei 14.133/2021. Cada informação cita a página e o
          trecho do edital de onde veio, e você confere com um clique. Depois, compare o edital
          com o perfil da sua empresa.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>
              <h2>Enviar um PDF</h2>
            </CardTitle>
            <CardDescription>Tem o edital no computador? Envie o arquivo.</CardDescription>
          </CardHeader>
          <CardContent>
            <UploadCard />
          </CardContent>
        </Card>
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>
              <h2>Buscar no PNCP</h2>
            </CardTitle>
            <CardDescription>
              Encontre contratações publicadas no Portal Nacional de Contratações Públicas e
              importe o edital sem baixar nada.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PncpSearch />
          </CardContent>
        </Card>
      </div>

      <section className="flex flex-col gap-3" aria-labelledby="recentes">
        <h2 id="recentes" className="text-xl font-semibold">
          Análises recentes
        </h2>
        <RecentAnalyses />
      </section>

      <Card size="sm">
        <CardHeader>
          <CardTitle>
            <h2>Status do sistema</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* The health check runs at request time; the rest of the page is static. */}
          <Suspense fallback={<p role="status">Verificando serviços…</p>}>
            <SystemStatus />
          </Suspense>
        </CardContent>
      </Card>
    </main>
  );
}

async function SystemStatus() {
  const health = await getBackendHealth();

  if (!health.reachable) {
    return (
      <div className="flex flex-col gap-3">
        <dl>
          <StatusRow label="API" ok={false} text="Fora do ar" />
        </dl>
        <p className="text-sm text-muted-foreground">
          Não foi possível falar com o backend. Confira se ele está rodando e
          recarregue a página.
        </p>
      </div>
    );
  }

  const databaseOk = health.database === "ok";
  return (
    <dl className="flex flex-col gap-3">
      <StatusRow label="API" ok text={`No ar (versão ${health.version})`} />
      <StatusRow
        label="Banco de dados"
        ok={databaseOk}
        text={databaseOk ? "Conectado" : "Sem conexão"}
      />
    </dl>
  );
}

function StatusRow({
  label,
  ok,
  text,
}: {
  label: string;
  ok: boolean;
  text: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="font-medium">{label}</dt>
      <dd>
        {/* The text carries the meaning; color only reinforces it. */}
        <Badge variant={ok ? "default" : "destructive"}>{text}</Badge>
      </dd>
    </div>
  );
}
