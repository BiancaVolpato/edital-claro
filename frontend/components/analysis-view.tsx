"use client";

import { AlertTriangle, Download, FileCheck2, Printer } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useCallback, useRef, useState } from "react";
import useSWR from "swr";

import { type PdfTarget } from "@/components/pdf-viewer";
import { PdfViewerLazy } from "@/components/pdf-viewer-lazy";
import { ConfidenceBadge, SeverityBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLocalStorage } from "@/lib/browser";
import { downloadFile, fetcher } from "@/lib/client";
import {
  CHECKLIST_SECTIONS,
  CITATION_STATUS_LABELS,
  FIELD_GROUPS,
  FIELD_LABELS,
  formatValue,
  isConfirmed,
} from "@/lib/format";
import type { Analysis, Audience, AudienceRisk, Citation, ExtractedField } from "@/lib/types";
import { cn } from "cn";

type Select = (citation: Citation) => void;

// --- Citations --------------------------------------------------------------------

export function CitationButtons({ citations, onSelect }: { citations: Citation[]; onSelect: Select }) {
  if (!citations.length) {
    return <span className="text-xs text-muted-foreground">sem citação</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {citations.map((citation, index) => {
        const confirmed = isConfirmed(citation);
        return (
          <button
            key={`${citation.page}-${index}`}
            type="button"
            onClick={() => onSelect(citation)}
            title={`"${citation.quote}" (${CITATION_STATUS_LABELS[citation.status]})`}
            aria-label={`Ver no edital, página ${citation.page}: ${CITATION_STATUS_LABELS[citation.status]}`}
            className={cn(
              "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              !confirmed && "border-amber-500 text-amber-900 dark:text-amber-200",
            )}
          >
            {!confirmed && <AlertTriangle className="size-3" aria-hidden />}
            p. {citation.page}
          </button>
        );
      })}
    </span>
  );
}

// --- Fields -------------------------------------------------------------------------

function FieldsPanel({ result, onSelect }: { result: Analysis["result"]; onSelect: Select }) {
  if (!result) return null;
  return (
    <div className="flex flex-col gap-6">
      {FIELD_GROUPS.map((group) => (
        <section key={group.title} aria-labelledby={`grupo-${group.title}`} className="flex flex-col gap-2">
          <h3 id={`grupo-${group.title}`} className="text-sm font-semibold">
            {group.title}
          </h3>
          <dl className="flex flex-col divide-y rounded-lg border">
            {group.fields.map((name) => {
              const field = result[name] as ExtractedField | undefined;
              if (!field) return null;
              return (
                <div
                  key={name}
                  className={cn(
                    "grid gap-1 p-3 sm:grid-cols-[10rem_1fr]",
                    field.needs_review && "bg-amber-50/60 dark:bg-amber-950/30",
                  )}
                >
                  <dt className="text-xs font-medium text-muted-foreground">{FIELD_LABELS[name]}</dt>
                  <dd className="flex flex-col gap-1.5">
                    <span className={cn("text-sm", field.value === null && "text-muted-foreground italic")}>
                      {formatValue(name, field.value)}
                    </span>
                    <span className="flex flex-wrap items-center gap-2">
                      {field.value !== null && (
                        <ConfidenceBadge confidence={field.confidence} needsReview={field.needs_review} />
                      )}
                      <CitationButtons citations={field.citations} onSelect={onSelect} />
                    </span>
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      ))}
    </div>
  );
}

// --- Checklist ----------------------------------------------------------------------

function ChecklistPanel({ analysisId, result, onSelect }: { analysisId: string; result: Analysis["result"]; onSelect: Select }) {
  // The ticks are a personal convenience, kept only in this browser.
  const [checked, setChecked] = useLocalStorage<Record<string, boolean>>(
    `checklist:${analysisId}`,
    {},
  );

  function toggle(key: string) {
    setChecked({ ...checked, [key]: !checked[key] });
  }

  if (!result) return null;
  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted-foreground">
        Documentos de habilitação pedidos no edital. Marque o que já tem; as marcações ficam só
        neste navegador.
      </p>
      {CHECKLIST_SECTIONS.map((section) => {
        const items = (result[section.field] as ExtractedField<string>[] | undefined) ?? [];
        return (
          <section key={section.field} className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">
              {section.title} <span className="font-normal text-muted-foreground">({items.length})</span>
            </h3>
            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground italic">Nenhum item encontrado no edital.</p>
            ) : (
              <ul className="flex flex-col divide-y rounded-lg border">
                {items.map((item, index) => {
                  const key = `${section.field}-${index}`;
                  return (
                    <li key={key} className={cn("flex gap-3 p-3", item.needs_review && "bg-amber-50/60 dark:bg-amber-950/30")}>
                      <input
                        type="checkbox"
                        id={key}
                        checked={!!checked[key]}
                        onChange={() => toggle(key)}
                        className="mt-0.5 size-4 shrink-0 accent-primary"
                      />
                      <div className="flex flex-col gap-1.5">
                        <label htmlFor={key} className={cn("text-sm", checked[key] && "text-muted-foreground line-through")}>
                          {item.value}
                        </label>
                        <span className="flex flex-wrap items-center gap-2">
                          {item.needs_review && <ConfidenceBadge confidence={item.confidence} needsReview />}
                          <CitationButtons citations={item.citations} onSelect={onSelect} />
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}

// --- Risks --------------------------------------------------------------------------

function RisksPanel({ analysis, onSelect }: { analysis: Analysis; onSelect: Select }) {
  const [audience, setAudience] = useState<Audience>("licitante");
  const { data, error, isLoading } = useSWR<{ risks: AudienceRisk[] }>(
    analysis.risks ? `/analyses/${analysis.id}/risks?audience=${audience}` : null,
    fetcher,
  );

  if (!analysis.risks) {
    return <p className="text-sm text-muted-foreground">A análise de riscos não está disponível para esta análise.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">Ver riscos para</legend>
        {(["licitante", "orgao"] as const).map((option) => (
          <Button
            key={option}
            variant={audience === option ? "default" : "outline"}
            size="sm"
            aria-pressed={audience === option}
            onClick={() => setAudience(option)}
          >
            {option === "licitante" ? "Para a empresa licitante" : "Para o órgão"}
          </Button>
        ))}
      </fieldset>
      {isLoading && <p role="status" className="text-sm">Carregando riscos…</p>}
      {error && <p className="text-sm text-destructive">{error.message}</p>}
      {data && data.risks.length === 0 && (
        <p className="text-sm text-muted-foreground">Nenhum risco apontado para este público.</p>
      )}
      <ul className="flex flex-col gap-3">
        {data?.risks.map((risk, index) => (
          <li key={`${risk.type}-${index}`}>
            <Card size="sm">
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={risk.severity} />
                  <Badge variant="outline">{risk.origin === "rule" ? "Regra automática" : "Análise por IA"}</Badge>
                </div>
                <CardTitle>
                  <h3>{risk.title}</h3>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p>{risk.description}</p>
                <p className="rounded-md bg-muted p-2">
                  <span className="font-medium">{audience === "licitante" ? "Orientação: " : "Alerta para o órgão: "}</span>
                  {risk.message}
                </p>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted-foreground">Trecho do edital:</span>
                  <CitationButtons citations={risk.citations} onSelect={onSelect} />
                </div>
                <details className="text-xs">
                  <summary className="cursor-pointer font-medium">
                    Fundamentação: {risk.legal_basis.map((b) => b.identifier).join("; ")}
                  </summary>
                  <ul className="mt-2 flex flex-col gap-2">
                    {risk.legal_basis.map((basis) => (
                      <li key={basis.identifier} className="rounded-md border p-2">
                        <p className="font-medium">{basis.citation}</p>
                        <p className="mt-1 whitespace-pre-line text-muted-foreground">{basis.text}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
      {analysis.risks.discarded.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground">
            {analysis.risks.discarded.length} achado(s) da IA descartado(s) por falta de trecho ou de artigo comprovado
          </summary>
          <ul className="mt-2 list-disc pl-5 text-muted-foreground">
            {analysis.risks.discarded.map((d) => (
              <li key={d.title}>
                {d.title}: {d.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// --- Progress -----------------------------------------------------------------------

function stepLabel(analysis: Analysis): string {
  const { steps_done: done, steps_total: total } = analysis;
  if (analysis.status === "pending") return "Na fila para começar";
  if (done === 0) return "Localizando as seções do edital";
  if (done < total - 3) return "Extraindo os dados do edital";
  return "Analisando riscos com base na Lei 14.133/2021";
}

function AnalysisProgress({ analysis }: { analysis: Analysis }) {
  const value = analysis.steps_total ? Math.round((analysis.steps_done / analysis.steps_total) * 100) : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h1>Analisando o edital</h1>
        </CardTitle>
        <CardDescription>
          A IA lê as seções do edital e cada resposta é conferida contra o texto do PDF. Pode
          levar alguns minutos; esta página se atualiza sozinha.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <Progress value={value} aria-label="Progresso da análise" />
        <p className="text-sm" role="status" aria-live="polite">
          {stepLabel(analysis)} ({analysis.steps_done} de {analysis.steps_total} etapas)
        </p>
      </CardContent>
    </Card>
  );
}

// --- Page ---------------------------------------------------------------------------

export function AnalysisView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const searchParams = useSearchParams();
  const viewer = useRef<HTMLDivElement>(null);
  const [target, setTarget] = useState<PdfTarget | null>(() => {
    const page = Number(searchParams.get("p"));
    return page > 0 ? { page, quote: searchParams.get("q"), key: 0 } : null;
  });
  const [exportError, setExportError] = useState<string | null>(null);

  const { data: analysis, error } = useSWR<Analysis>(`/analyses/${id}`, fetcher, {
    refreshInterval: (latest) =>
      latest && (latest.status === "pending" || latest.status === "running") ? 2000 : 0,
  });

  const select = useCallback((citation: Citation) => {
    setTarget((current) => ({ page: citation.page, quote: citation.quote, key: (current?.key ?? 0) + 1 }));
    // On narrow screens the viewer is below the panels: bring it into view.
    if (window.matchMedia("(max-width: 1023px)").matches) {
      viewer.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  async function exportMarkdown() {
    setExportError(null);
    try {
      await downloadFile(`/analyses/${id}/report.md`, `analise-${id}.md`);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Falha ao exportar.");
    }
  }

  if (error) {
    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <Alert variant="destructive">
          <AlertTitle>Análise indisponível</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      </main>
    );
  }
  if (!analysis) {
    return <main className="mx-auto w-full max-w-3xl px-4 py-10"><p role="status">Carregando análise…</p></main>;
  }
  if (analysis.status === "pending" || analysis.status === "running") {
    return (
      <main className="mx-auto w-full max-w-3xl px-4 py-10">
        <AnalysisProgress analysis={analysis} />
      </main>
    );
  }
  if (analysis.status === "failed" && !analysis.result) {
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-10">
        <Alert variant="destructive">
          <AlertTitle>A análise falhou</AlertTitle>
          <AlertDescription>{analysis.error ?? "Erro inesperado."}</AlertDescription>
        </Alert>
        <Link href={`/documentos/${analysis.document_id}`} className={buttonVariants({ variant: "outline" })}>
          Voltar ao documento
        </Link>
      </main>
    );
  }

  const result = analysis.result;
  const object = (result?.object as ExtractedField<string> | undefined)?.value;
  const agency = (result?.agency as ExtractedField<string> | undefined)?.value;
  const counts = analysis.citation_counts;
  const reviewCount = result
    ? Object.values(result).flat().filter((f) => (f as ExtractedField).needs_review && (f as ExtractedField).value !== null).length
    : 0;

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-sm text-muted-foreground">{agency ?? "Análise do edital"}</p>
          <h1 className="text-2xl font-semibold break-words">{object ?? "Edital analisado"}</h1>
          <p className="text-xs text-muted-foreground">
            {counts.valid ?? 0} de {counts.total ?? 0} citações confirmadas no texto do edital
            {reviewCount > 0 && ` · ${reviewCount} item(ns) para revisar`}
            {analysis.cost_usd !== null && ` · custo estimado US$ ${analysis.cost_usd.toFixed(2)}`}
            {` · ${analysis.llm_model}, prompt ${analysis.prompt_version}`}
          </p>
        </div>
        <div className="no-print flex flex-wrap gap-2">
          <Link href={`/analises/${id}/aptidao`} className={buttonVariants()}>
            <FileCheck2 aria-hidden /> Verificar aptidão
          </Link>
          <Button variant="outline" onClick={exportMarkdown}>
            <Download aria-hidden /> Exportar Markdown
          </Button>
          <Button variant="outline" onClick={() => window.print()}>
            <Printer aria-hidden /> Imprimir ou salvar PDF
          </Button>
        </div>
      </header>

      {exportError && (
        <Alert variant="destructive">
          <AlertDescription>{exportError}</AlertDescription>
        </Alert>
      )}
      {analysis.warnings.length > 0 && (
        <Alert>
          <AlertTitle>Avisos da análise</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {analysis.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid flex-1 gap-6 lg:grid-cols-2">
        <Tabs defaultValue="campos" className="min-w-0">
          <TabsList className="no-print">
            <TabsTrigger value="campos">Campos</TabsTrigger>
            <TabsTrigger value="checklist">Checklist</TabsTrigger>
            <TabsTrigger value="riscos">Riscos</TabsTrigger>
          </TabsList>
          <TabsContent value="campos">
            <FieldsPanel result={result} onSelect={select} />
          </TabsContent>
          <TabsContent value="checklist">
            <ChecklistPanel analysisId={id} result={result} onSelect={select} />
          </TabsContent>
          <TabsContent value="riscos">
            <RisksPanel analysis={analysis} onSelect={select} />
          </TabsContent>
        </Tabs>

        <section
          ref={viewer}
          aria-label="Edital em PDF"
          className="no-print h-[85vh] lg:sticky lg:top-4"
        >
          <PdfViewerLazy url={`/api/documents/${analysis.document_id}/file`} target={target} />
        </section>
      </div>
    </main>
  );
}
