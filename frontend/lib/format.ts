// Labels and value formatting in Portuguese, matching backend/app/reports/markdown.py.

import type { Citation, RequirementStatus, Severity } from "@/lib/types";

export const FIELD_LABELS: Record<string, string> = {
  number: "Número",
  modality: "Modalidade",
  agency: "Órgão",
  object: "Objeto",
  estimated_value: "Valor estimado",
  judgment_criterion: "Critério de julgamento",
  execution_regime: "Regime de execução",
  publication_date: "Data de publicação",
  opening: "Abertura da sessão",
  impugnation_deadline: "Prazo de impugnação",
  clarification_deadline: "Prazo de esclarecimentos",
  execution_period: "Prazo de execução",
  bid_guarantee: "Garantia de proposta",
  contract_guarantee: "Garantia contratual",
  site_visit: "Visita técnica",
  consortium_allowed: "Consórcio permitido",
  me_epp_exclusive: "Exclusiva para ME/EPP",
};

export const FIELD_GROUPS: { title: string; fields: string[] }[] = [
  {
    title: "Identificação",
    fields: [
      "number",
      "modality",
      "agency",
      "object",
      "estimated_value",
      "judgment_criterion",
      "execution_regime",
    ],
  },
  {
    title: "Datas e prazos",
    fields: [
      "publication_date",
      "opening",
      "impugnation_deadline",
      "clarification_deadline",
      "execution_period",
    ],
  },
  {
    title: "Garantias e participação",
    fields: [
      "bid_guarantee",
      "contract_guarantee",
      "site_visit",
      "consortium_allowed",
      "me_epp_exclusive",
    ],
  },
];

export const CHECKLIST_SECTIONS: { field: string; title: string }[] = [
  { field: "qualification_legal", title: "Habilitação jurídica" },
  { field: "qualification_fiscal", title: "Regularidade fiscal, social e trabalhista" },
  { field: "qualification_technical", title: "Qualificação técnica" },
  { field: "qualification_economic", title: "Qualificação econômico-financeira" },
  { field: "annexes", title: "Anexos" },
];

export const SEVERITY_LABELS: Record<Severity, string> = {
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
};

export const STATUS_LABELS: Record<RequirementStatus, string> = {
  atende: "Atende",
  nao_atende: "Não atende",
  nao_verificavel: "Verificar",
};

export const VERDICT_LABELS = {
  apto: "Apto",
  apto_com_ressalvas: "Apto, com itens a conferir",
  inapto: "Inapto",
} as const;

export const CITATION_STATUS_LABELS: Record<Citation["status"], string> = {
  valid: "trecho confirmado",
  wrong_page: "trecho confirmado em outra página",
  not_found: "trecho não encontrado no edital",
  too_short: "trecho curto demais para comprovar",
};

export function isConfirmed(citation: Citation): boolean {
  return citation.status === "valid" || citation.status === "wrong_page";
}

const brlFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export function brl(value: number): string {
  return brlFormatter.format(value);
}

/** "2026-10-15" or an ISO date-time -> "15/10/2026" (no timezone shift). */
export function brDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

/** Timestamps with a timezone (from the database) are shown in the viewer's time;
 *  local date-times (from the PNCP) are shown as written. */
export function brDateTime(value: string): string {
  if (/(Z|[+-]\d{2}:\d{2})$/.test(value)) {
    return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }
  const time = value.slice(11, 16);
  return time ? `${brDate(value)} ${time}` : brDate(value);
}

/** A field value as a person reads it (same rules as the Markdown export). */
export function formatValue(name: string, value: unknown): string {
  if (value === null || value === undefined) return "Não encontrado";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (name === "estimated_value" && typeof value === "number") return brl(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) return brDate(value);
  if (typeof value === "object") {
    const v = value as Record<string, unknown>;
    if ("time" in v && "date" in v) {
      return `${brDate(String(v.date))}${v.time ? ` às ${v.time}` : ""}`;
    }
    if ("rule" in v) {
      const parts = [v.date ? brDate(String(v.date)) : null, v.rule as string | null];
      return parts.filter(Boolean).join(" — ") || "Não encontrado";
    }
    if ("amount" in v) return `${v.amount} ${v.unit}`;
    if ("required" in v) {
      if (!v.required) return "Não exigida";
      return typeof v.percent === "number"
        ? `Exigida (${String(v.percent).replace(".", ",")}%)`
        : "Exigida";
    }
  }
  if (typeof value === "string" && value.includes("_") && !value.includes(" ")) {
    const text = value.replaceAll("_", " ");
    return text.charAt(0).toUpperCase() + text.slice(1);
  }
  return String(value);
}
