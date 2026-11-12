import { Badge } from "@/components/ui/badge";
import { SEVERITY_LABELS, STATUS_LABELS } from "@/lib/format";
import type { AnalysisStatus, RequirementStatus, Severity } from "@/lib/types";
import { cn } from "cn";

// Text carries the meaning; color only reinforces it (contrast checked on both themes).
const SEVERITY_STYLES: Record<Severity, string> = {
  alta: "bg-red-700 text-white dark:bg-red-600",
  media: "bg-amber-300 text-amber-950 dark:bg-amber-400",
  baixa: "bg-sky-100 text-sky-950 dark:bg-sky-200",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge className={cn("border-transparent", SEVERITY_STYLES[severity])}>
      Severidade {SEVERITY_LABELS[severity].toLowerCase()}
    </Badge>
  );
}

const REQUIREMENT_STYLES: Record<RequirementStatus, string> = {
  atende: "bg-emerald-700 text-white dark:bg-emerald-600",
  nao_atende: "bg-red-700 text-white dark:bg-red-600",
  nao_verificavel: "bg-amber-300 text-amber-950 dark:bg-amber-400",
};

export function RequirementBadge({ status }: { status: RequirementStatus }) {
  return (
    <Badge className={cn("border-transparent", REQUIREMENT_STYLES[status])}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}

const ANALYSIS_LABELS: Record<AnalysisStatus, string> = {
  pending: "Na fila",
  running: "Em andamento",
  completed: "Concluída",
  failed: "Falhou",
};

export function AnalysisStatusBadge({ status }: { status: AnalysisStatus }) {
  return (
    <Badge variant={status === "failed" ? "destructive" : status === "completed" ? "default" : "secondary"}>
      {ANALYSIS_LABELS[status]}
    </Badge>
  );
}

export function ConfidenceBadge({ confidence, needsReview }: { confidence: number; needsReview: boolean }) {
  const value = Math.round(confidence * 100);
  return (
    <Badge
      variant="outline"
      className={cn(needsReview && "border-amber-500 bg-amber-50 text-amber-950 dark:bg-amber-950 dark:text-amber-100")}
      title="Confiança após conferir as citações contra o texto do edital"
    >
      {needsReview ? `Revisar · ${value}%` : `Confiança ${value}%`}
    </Badge>
  );
}
