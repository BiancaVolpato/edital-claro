import { Suspense } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getBackendHealth } from "@/lib/api";

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-16">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">Edital Claro</h1>
        <p className="text-muted-foreground">
          Análise de editais de obras públicas com IA. Cada informação extraída
          cita a página e o trecho do edital de onde veio.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Status do sistema</h2>
          </CardTitle>
          <CardDescription>
            Verificação feita a cada carregamento desta página.
          </CardDescription>
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
