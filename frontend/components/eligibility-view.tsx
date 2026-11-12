"use client";

import { Download, Printer } from "lucide-react";
import Link from "next/link";
import { use, useId, useState } from "react";
import useSWR from "swr";

import { RequirementBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { downloadFile, fetcher, postJson } from "@/lib/client";
import { brDate, brDateTime, isConfirmed, STATUS_LABELS, VERDICT_LABELS } from "@/lib/format";
import type { CompanyProfile, EligibilityCheck, RequirementResult, RequirementStatus } from "@/lib/types";
import { cn } from "cn";

const SECTION_TITLES: Record<RequirementResult["section"], string> = {
  participacao: "Participação",
  juridica: "Habilitação jurídica",
  fiscal: "Regularidade fiscal, social e trabalhista",
  tecnica: "Qualificação técnica",
  economica: "Qualificação econômico-financeira",
};

const VERDICT_STYLES = {
  apto: "border-emerald-600 bg-emerald-50 dark:bg-emerald-950/40",
  apto_com_ressalvas: "border-amber-500 bg-amber-50 dark:bg-amber-950/40",
  inapto: "border-red-600 bg-red-50 dark:bg-red-950/40",
} as const;

function citationHref(analysisId: string, page: number, quote: string): string {
  return `/analises/${analysisId}?${new URLSearchParams({ p: String(page), q: quote })}`;
}

function Report({ analysisId, check }: { analysisId: string; check: EligibilityCheck }) {
  const { report } = check;
  const { summary } = report;
  const [exportError, setExportError] = useState<string | null>(null);
  const [filter, setFilter] = useState<RequirementStatus | "todas">("todas");
  const shown = report.results.filter((r) => filter === "todas" || r.status === filter);
  const sections = Object.keys(SECTION_TITLES) as RequirementResult["section"][];

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="veredito" className={cn("flex flex-col gap-2 rounded-xl border-2 p-4", VERDICT_STYLES[summary.verdict])}>
        <p className="text-sm text-muted-foreground">Veredito para {check.profile_snapshot.name}</p>
        <h2 id="veredito" className="text-2xl font-semibold">{VERDICT_LABELS[summary.verdict]}</h2>
        <p>{summary.message}</p>
        <p className="text-sm">
          {summary.counts.atende} atendem · {summary.counts.nao_atende} não atendem · {summary.counts.nao_verificavel} para verificar ·
          validades conferidas em {brDate(report.reference_date)}
        </p>
        <div className="no-print flex flex-wrap gap-2 pt-1">
          <Button
            variant="outline"
            onClick={async () => {
              setExportError(null);
              try {
                await downloadFile(`/eligibility/${check.id}/report.md`, `aptidao-${check.id}.md`);
              } catch (e) {
                setExportError(e instanceof Error ? e.message : "Falha ao exportar.");
              }
            }}
          >
            <Download aria-hidden /> Exportar Markdown
          </Button>
          <Button variant="outline" onClick={() => window.print()}>
            <Printer aria-hidden /> Imprimir ou salvar PDF
          </Button>
        </div>
        {exportError && <p className="text-sm text-destructive">{exportError}</p>}
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <Card size="sm">
          <CardHeader>
            <CardTitle>
              <h2>O que falta</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summary.missing.length === 0 ? (
              <p className="text-muted-foreground">Nada pendente entre os itens conferidos.</p>
            ) : (
              <ul className="list-disc space-y-1 pl-4">
                {summary.missing.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle>
              <h2>Prazos críticos</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summary.deadlines.length === 0 ? (
              <p className="text-muted-foreground">Nenhum prazo identificado.</p>
            ) : (
              <ul className="space-y-1">
                {summary.deadlines.map((d) => (
                  <li key={`${d.label}-${d.date}`} className="flex gap-2">
                    <span className="min-w-24 font-medium">{d.date ? brDate(d.date) : (d.rule ?? "sem data")}</span>
                    <span>
                      {d.label}
                      {d.source === "perfil" && <span className="text-muted-foreground"> (perfil)</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {report.warnings.length > 0 && (
        <Alert>
          <AlertTitle>Avisos</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {report.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <section aria-labelledby="exigencias" className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="exigencias" className="text-xl font-semibold">Exigências do edital</h2>
          <fieldset className="no-print flex flex-wrap gap-1">
            <legend className="sr-only">Filtrar exigências</legend>
            {(["todas", "nao_atende", "nao_verificavel", "atende"] as const).map((option) => (
              <Button key={option} size="sm" variant={filter === option ? "default" : "outline"} aria-pressed={filter === option} onClick={() => setFilter(option)}>
                {option === "todas" ? "Todas" : STATUS_LABELS[option]}
              </Button>
            ))}
          </fieldset>
        </div>
        {shown.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma exigência neste filtro.</p>}
        {sections.map((section) => {
          const items = shown.filter((r) => r.section === section);
          if (!items.length) return null;
          return (
            <div key={section} className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">{SECTION_TITLES[section]}</h3>
              <ul className="flex flex-col divide-y rounded-lg border">
                {items.map((result, index) => (
                  <li key={`${section}-${index}`} className="flex flex-col gap-1.5 p-3">
                    <div className="flex flex-wrap items-start gap-2">
                      <RequirementBadge status={result.status} />
                      {result.origin === "llm" && (
                        <span className="text-xs text-muted-foreground">(comparação de atestados com IA)</span>
                      )}
                    </div>
                    <p className="text-sm">{result.requirement}</p>
                    <p className="text-sm text-muted-foreground">{result.reason}</p>
                    {result.evidence.length > 0 && (
                      <p className="text-xs text-muted-foreground">Do perfil: {result.evidence.join("; ")}</p>
                    )}
                    <p className="flex flex-wrap items-center gap-2 text-xs">
                      {result.requirement_needs_review && (
                        <span className="text-amber-800 dark:text-amber-200">Exigência extraída com baixa confiança: confira no edital.</span>
                      )}
                      {result.citations.filter(isConfirmed).map((c) => (
                        <Link key={`${c.page}-${c.quote}`} href={citationHref(analysisId, c.page, c.quote)} className="rounded-md border px-1.5 py-0.5 font-medium hover:bg-muted">
                          Ver no edital, p. {c.page}
                        </Link>
                      ))}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </div>
  );
}

export function EligibilityView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const selectId = useId();
  const { data: profiles, error: profilesError } = useSWR<CompanyProfile[]>("/profiles", fetcher);
  const [profileId, setProfileId] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<EligibilityCheck | null>(null);
  // Checks made before (e.g. the one seeded in the demo, made with the AI): the
  // newest is shown until a new check is run.
  const { data: stored } = useSWR<EligibilityCheck[]>(`/analyses/${id}/eligibility`, fetcher);
  const shown = check ?? stored?.[0] ?? null;

  async function run(event: React.FormEvent) {
    event.preventDefault();
    const chosen = profileId || profiles?.[0]?.id;
    if (!chosen) return;
    setRunning(true);
    setError(null);
    try {
      setCheck(await postJson<EligibilityCheck>(`/analyses/${id}/eligibility`, { profile_id: chosen }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível verificar.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <Link href={`/analises/${id}`} className="no-print text-sm text-muted-foreground hover:underline">
          ← Voltar à análise
        </Link>
        <h1 className="text-2xl font-semibold">Aptidão da empresa</h1>
        <p className="text-sm text-muted-foreground">
          Compara o perfil da empresa com cada exigência de habilitação do edital. Datas, valores e
          quantidades são comparados por regras; a IA só diz se um atestado é do mesmo tipo de
          serviço pedido.
        </p>
      </header>

      <Card className="no-print">
        <CardHeader>
          <CardTitle>
            <h2>Escolha o perfil</h2>
          </CardTitle>
          <CardDescription>A verificação leva alguns segundos.</CardDescription>
        </CardHeader>
        <CardContent>
          {profilesError && <p className="text-sm text-destructive">{profilesError.message}</p>}
          {profiles && profiles.length === 0 ? (
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm text-muted-foreground">Nenhum perfil cadastrado.</p>
              <Link href="/perfis/novo" className={buttonVariants({ variant: "outline" })}>
                Cadastrar um perfil
              </Link>
            </div>
          ) : (
            <form onSubmit={run} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="flex flex-1 flex-col gap-1.5">
                <Label htmlFor={selectId}>Perfil da empresa</Label>
                <select
                  id={selectId}
                  className="h-9 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
                  value={profileId || profiles?.[0]?.id || ""}
                  onChange={(e) => setProfileId(e.target.value)}
                  disabled={!profiles}
                >
                  {profiles?.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <Button type="submit" size="lg" disabled={running || !profiles?.length}>
                {running ? "Verificando…" : "Verificar aptidão"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {running && <p role="status">Comparando o perfil com as exigências…</p>}
      {!check && shown && (
        <p className="text-sm text-muted-foreground">
          Última verificação salva: {brDateTime(shown.created_at)}, perfil{" "}
          {shown.profile_snapshot.name},{" "}
          {shown.llm_model ? `comparação de atestados com IA (${shown.llm_model})` : "sem a etapa de IA"}.
        </p>
      )}
      {shown && <Report key={shown.id} analysisId={id} check={shown} />}
    </main>
  );
}
