"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import useSWR from "swr";

import { AnalysisStatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { fetcher, postJson } from "@/lib/client";
import { brDateTime, brl } from "@/lib/format";
import type { Analysis, AnalysisSummary, DocumentDetail } from "@/lib/types";

export function DocumentView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { data: document, error } = useSWR<DocumentDetail>(`/documents/${id}`, fetcher, {
    // Poll while the PDF is being read.
    refreshInterval: (latest) =>
      latest && (latest.status === "pending" || latest.status === "processing") ? 1500 : 0,
  });
  const { data: analyses } = useSWR<AnalysisSummary[]>(
    document?.status === "ready" ? `/analyses?document_id=${id}` : null,
    fetcher,
  );

  async function analyze() {
    setStarting(true);
    setStartError(null);
    try {
      const analysis = await postJson<Analysis>(`/documents/${id}/analyze`, {});
      router.push(`/analises/${analysis.id}`);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Não foi possível iniciar a análise.");
      setStarting(false);
    }
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Documento indisponível</AlertTitle>
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!document) {
    return <p role="status">Carregando documento…</p>;
  }

  const pncp = document.metadata.pncp;
  const reading = document.status === "pending" || document.status === "processing";
  return (
    <>
      <header className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">
          {document.source === "pncp" ? "Importado do PNCP" : "Enviado por upload"}
        </p>
        <h1 className="text-2xl font-semibold break-words">{pncp?.object ?? document.filename}</h1>
        {pncp && (
          <p className="text-sm text-muted-foreground">
            {[pncp.agency, pncp.municipality && `${pncp.municipality}/${pncp.uf}`, pncp.estimated_value ? `valor estimado ${brl(pncp.estimated_value)}` : null, pncp.control_number]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </header>

      {reading && (
        <Card>
          <CardHeader>
            <CardTitle>Lendo o PDF</CardTitle>
            <CardDescription>
              Extraindo o texto de cada página; páginas escaneadas passam por OCR, o que pode levar
              alguns minutos.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Progress value={null} aria-label="Lendo o PDF" />
          </CardContent>
        </Card>
      )}

      {document.status === "failed" && (
        <Alert variant="destructive">
          <AlertTitle>Não foi possível ler este PDF</AlertTitle>
          <AlertDescription>{document.error}</AlertDescription>
        </Alert>
      )}

      {document.status === "ready" && (
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Pronto para analisar</h2>
            </CardTitle>
            <CardDescription>
              {document.page_count} páginas lidas
              {document.metadata.ocr_pages?.length
                ? `, ${document.metadata.ocr_pages.length} por OCR`
                : ""}
              . A análise usa IA (com custo) e leva de um a alguns minutos.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {document.metadata.warnings?.map((warning) => (
              <Alert key={warning}>
                <AlertDescription>{warning}</AlertDescription>
              </Alert>
            ))}
            {startError && (
              <Alert variant="destructive">
                <AlertDescription>{startError}</AlertDescription>
              </Alert>
            )}
            <Button size="lg" onClick={analyze} disabled={starting}>
              {starting ? "Iniciando…" : analyses?.length ? "Analisar de novo" : "Analisar com IA"}
            </Button>
            {analyses && analyses.length > 0 && (
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">Análises deste documento</h3>
                <ul className="flex flex-col divide-y rounded-lg border">
                  {analyses.map((a) => (
                    <li key={a.id}>
                      <Link href={`/analises/${a.id}`} className="flex items-center justify-between gap-3 p-3 text-sm hover:bg-muted/50">
                        <span>{brDateTime(a.created_at)}</span>
                        <AnalysisStatusBadge status={a.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}
