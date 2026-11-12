"use client";

import Link from "next/link";
import useSWR from "swr";

import { AnalysisStatusBadge } from "@/components/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { fetcher } from "@/lib/client";
import { brDateTime } from "@/lib/format";
import type { AnalysisSummary } from "@/lib/types";

export function RecentAnalyses() {
  const { data, error, isLoading } = useSWR<AnalysisSummary[]>("/analyses?limit=10", fetcher);

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2" role="status" aria-label="Carregando análises">
        <Skeleton className="h-14" />
        <Skeleton className="h-14" />
      </div>
    );
  }
  if (error) {
    return <p className="text-sm text-muted-foreground">Não foi possível carregar as análises: {error.message}</p>;
  }
  if (!data?.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Nenhuma análise ainda. Envie um edital ou importe um do PNCP para começar.
      </p>
    );
  }
  return (
    <ul className="flex flex-col divide-y rounded-lg border">
      {data.map((analysis) => (
        <li key={analysis.id}>
          <Link
            href={`/analises/${analysis.id}`}
            className="flex flex-col gap-1 p-3 transition-colors hover:bg-muted/50 focus-visible:bg-muted sm:flex-row sm:items-center sm:justify-between"
          >
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-medium">{analysis.object ?? analysis.filename}</span>
              <span className="truncate text-xs text-muted-foreground">
                {[analysis.agency, analysis.filename, brDateTime(analysis.created_at)].filter(Boolean).join(" · ")}
              </span>
            </span>
            <AnalysisStatusBadge status={analysis.status} />
          </Link>
        </li>
      ))}
    </ul>
  );
}
