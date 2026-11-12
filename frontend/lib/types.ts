// Types of the backend API responses used by the interface. They mirror the
// Pydantic models in backend/app (field names stay as the API sends them).

export type CitationStatus = "valid" | "wrong_page" | "not_found" | "too_short";

export type Citation = {
  page: number;
  quote: string;
  status: CitationStatus;
  cited_page: number;
  match_score: number;
};

export type ExtractedField<T = unknown> = {
  value: T | null;
  citations: Citation[];
  confidence: number;
  needs_review: boolean;
};

export type Extraction = Record<string, ExtractedField | ExtractedField<string>[]>;

export type Severity = "alta" | "media" | "baixa";
export type Audience = "licitante" | "orgao";

export type LegalBasis = { citation: string; identifier: string; text: string };

export type AudienceRisk = {
  type: string;
  severity: Severity;
  title: string;
  message: string;
  description: string;
  citations: Citation[];
  legal_basis: LegalBasis[];
  origin: "rule" | "llm";
};

export type RiskReport = {
  risks: unknown[];
  discarded: { title: string; reason: string }[];
  warnings: string[];
};

export type AnalysisStatus = "pending" | "running" | "completed" | "failed";

export type Analysis = {
  id: string;
  document_id: string;
  status: AnalysisStatus;
  error: string | null;
  steps_done: number;
  steps_total: number;
  prompt_version: string;
  prompt_hash: string;
  llm_model: string;
  result: Extraction | null;
  risks: RiskReport | null;
  citation_counts: Record<string, number>;
  warnings: string[];
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms: number | null;
  created_at: string;
  completed_at: string | null;
};

export type AnalysisSummary = {
  id: string;
  document_id: string;
  filename: string;
  status: AnalysisStatus;
  steps_done: number;
  steps_total: number;
  object: string | null;
  agency: string | null;
  created_at: string;
  completed_at: string | null;
};

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export type DocumentDetail = {
  id: string;
  source: "upload" | "pncp";
  source_ref: string | null;
  filename: string;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  metadata: {
    warnings?: string[];
    ocr_pages?: number[];
    pncp?: Procurement;
  };
  chunk_count?: number;
  created_at: string;
};

export type Procurement = {
  control_number: string;
  cnpj: string;
  year: number;
  sequential: number;
  number: string | null;
  object: string;
  modality_name: string | null;
  agency: string | null;
  unit: string | null;
  municipality: string | null;
  uf: string | null;
  estimated_value: number | null;
  status: string | null;
  published_at: string | null;
  proposals_from: string | null;
  proposals_until: string | null;
};

export type PncpSearchResponse = {
  results: Procurement[];
  total_matches: number;
  scanned: number;
  truncated: boolean;
  warnings: string[];
};

export type PncpImportResponse = {
  procurement: Procurement;
  documents: { document: DocumentDetail; duplicate: boolean }[];
  skipped: string[];
};

// --- Company profile and eligibility -------------------------------------------

export type CompanySize = "ME" | "EPP" | "demais";
export type CertificateKind =
  | "federal"
  | "estadual"
  | "municipal"
  | "fgts"
  | "trabalhista"
  | "falencia";
export type QuantityUnit = "m2" | "m3" | "m" | "t" | "un";

export type CompanyProfileData = {
  name: string;
  cnpj: string | null;
  size: CompanySize;
  cnaes: string[];
  share_capital: number | null;
  net_worth: number | null;
  attestations: {
    description: string;
    issuer: string | null;
    quantities: { service: string; quantity: number; unit: QuantityUnit }[];
  }[];
  certificates: { kind: CertificateKind; valid_until: string }[];
  registration: {
    council: "CREA" | "CAU";
    number: string;
    state: string | null;
    valid_until: string | null;
  } | null;
};

export type CompanyProfile = CompanyProfileData & {
  id: string;
  created_at: string;
  updated_at: string;
};

export type RequirementStatus = "atende" | "nao_atende" | "nao_verificavel";

export type RequirementResult = {
  section: "participacao" | "juridica" | "fiscal" | "tecnica" | "economica";
  kind: string;
  requirement: string;
  citations: Citation[];
  requirement_needs_review: boolean;
  status: RequirementStatus;
  reason: string;
  evidence: string[];
  origin: "code" | "llm";
};

export type EligibilityCheck = {
  id: string;
  analysis_id: string;
  profile_id: string | null;
  profile_snapshot: CompanyProfileData;
  report: {
    reference_date: string;
    results: RequirementResult[];
    warnings: string[];
    summary: {
      verdict: "apto" | "apto_com_ressalvas" | "inapto";
      message: string;
      counts: Record<RequirementStatus, number>;
      missing: string[];
      deadlines: {
        label: string;
        date: string | null;
        rule: string | null;
        source: "edital" | "perfil";
        citations: Citation[];
      }[];
    };
  };
  llm_model: string | null;
  cost_usd: number | null;
  created_at: string;
};
