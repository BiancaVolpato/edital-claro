"use client";

import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { postJson } from "@/lib/client";
import type {
  CertificateKind,
  CompanyProfile,
  CompanyProfileData,
  CompanySize,
  QuantityUnit,
} from "@/lib/types";

const CERTIFICATES: { kind: CertificateKind; label: string }[] = [
  { kind: "federal", label: "Fazenda Federal (tributos federais e dívida ativa)" },
  { kind: "estadual", label: "Fazenda Estadual" },
  { kind: "municipal", label: "Fazenda Municipal" },
  { kind: "fgts", label: "FGTS (CRF)" },
  { kind: "trabalhista", label: "Débitos trabalhistas (CNDT)" },
  { kind: "falencia", label: "Falência e recuperação judicial" },
];
const UNITS: { value: QuantityUnit; label: string }[] = [
  { value: "m2", label: "m²" },
  { value: "m3", label: "m³" },
  { value: "m", label: "m" },
  { value: "t", label: "t" },
  { value: "un", label: "un" },
];
const SELECT =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

type Quantity = { service: string; quantity: string; unit: QuantityUnit };
type Attestation = { description: string; issuer: string; quantities: Quantity[] };
type FormState = {
  name: string;
  cnpj: string;
  size: CompanySize;
  cnaes: string;
  shareCapital: string;
  netWorth: string;
  hasRegistration: boolean;
  council: "CREA" | "CAU";
  registrationNumber: string;
  registrationState: string;
  registrationValidUntil: string;
  certificates: Record<CertificateKind, string>;
  attestations: Attestation[];
};

function toForm(profile?: CompanyProfileData): FormState {
  const certificates = Object.fromEntries(CERTIFICATES.map((c) => [c.kind, ""])) as Record<CertificateKind, string>;
  for (const c of profile?.certificates ?? []) certificates[c.kind] = c.valid_until;
  return {
    name: profile?.name ?? "",
    cnpj: profile?.cnpj ?? "",
    size: profile?.size ?? "EPP",
    cnaes: (profile?.cnaes ?? []).map((c) => `${c.slice(0, 4)}-${c[4]}/${c.slice(5)}`).join(", "),
    shareCapital: profile?.share_capital?.toString() ?? "",
    netWorth: profile?.net_worth?.toString() ?? "",
    hasRegistration: !!profile?.registration || !profile,
    council: profile?.registration?.council ?? "CREA",
    registrationNumber: profile?.registration?.number ?? "",
    registrationState: profile?.registration?.state ?? "",
    registrationValidUntil: profile?.registration?.valid_until ?? "",
    certificates,
    attestations: (profile?.attestations ?? []).map((a) => ({
      description: a.description,
      issuer: a.issuer ?? "",
      quantities: a.quantities.map((q) => ({ ...q, quantity: String(q.quantity) })),
    })),
  };
}

/** Brazilian or plain notation: "1.500,50", "1500,5", "1.500" and "1500.5" all work. */
function number(value: string): number | null {
  let text = value.trim().replace(/^R\$\s*/, "");
  if (!text) return null;
  if (text.includes(",")) text = text.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(text)) text = text.replace(/\./g, "");
  return Number(text);
}

function toPayload(form: FormState): CompanyProfileData {
  return {
    name: form.name.trim(),
    cnpj: form.cnpj.trim() || null,
    size: form.size,
    cnaes: form.cnaes.split(/[,;\n]/).map((c) => c.trim()).filter(Boolean),
    share_capital: number(form.shareCapital),
    net_worth: number(form.netWorth),
    registration: form.hasRegistration
      ? {
          council: form.council,
          number: form.registrationNumber.trim(),
          state: form.registrationState.trim() || null,
          valid_until: form.registrationValidUntil || null,
        }
      : null,
    certificates: CERTIFICATES.filter((c) => form.certificates[c.kind]).map((c) => ({
      kind: c.kind,
      valid_until: form.certificates[c.kind],
    })),
    attestations: form.attestations.map((a) => ({
      description: a.description.trim(),
      issuer: a.issuer.trim() || null,
      quantities: a.quantities.map((q) => ({
        service: q.service.trim(),
        quantity: number(q.quantity) ?? 0,
        unit: q.unit,
      })),
    })),
  };
}

export function ProfileForm({ profile }: { profile?: CompanyProfile }) {
  const router = useRouter();
  const id = useId();
  const [form, setForm] = useState<FormState>(() => toForm(profile));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  function updateAttestation(index: number, change: Partial<Attestation>) {
    setForm((current) => ({
      ...current,
      attestations: current.attestations.map((a, i) => (i === index ? { ...a, ...change } : a)),
    }));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const saved = profile
        ? await postJson<CompanyProfile>(`/profiles/${profile.id}`, toPayload(form), "PUT")
        : await postJson<CompanyProfile>("/profiles", toPayload(form));
      router.push(`/perfis?salvo=${saved.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Não foi possível salvar.");
      setSaving(false);
    }
  }

  const field = (name: string) => `${id}-${name}`;

  return (
    <form onSubmit={save} className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Empresa</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor={field("name")}>Razão social</Label>
            <Input id={field("name")} required minLength={2} value={form.name} onChange={(e) => update("name", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={field("cnpj")}>CNPJ</Label>
            <Input id={field("cnpj")} inputMode="numeric" placeholder="00.000.000/0000-00" value={form.cnpj} onChange={(e) => update("cnpj", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={field("size")}>Porte</Label>
            <select id={field("size")} className={SELECT} value={form.size} onChange={(e) => update("size", e.target.value as CompanySize)}>
              <option value="ME">Microempresa (ME)</option>
              <option value="EPP">Empresa de pequeno porte (EPP)</option>
              <option value="demais">Demais</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor={field("cnaes")}>CNAEs (separados por vírgula)</Label>
            <Input id={field("cnaes")} placeholder="4211-1/01, 4213-8/00" value={form.cnaes} onChange={(e) => update("cnaes", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={field("capital")}>Capital social (R$)</Label>
            <Input id={field("capital")} inputMode="decimal" placeholder="300000" value={form.shareCapital} onChange={(e) => update("shareCapital", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={field("networth")}>Patrimônio líquido do último balanço (R$)</Label>
            <Input id={field("networth")} inputMode="decimal" placeholder="450000" value={form.netWorth} onChange={(e) => update("netWorth", e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Registro no conselho profissional</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-4">
          <label className="flex items-center gap-2 text-sm sm:col-span-4">
            <input type="checkbox" className="size-4 accent-primary" checked={form.hasRegistration} onChange={(e) => update("hasRegistration", e.target.checked)} />
            A empresa tem registro no CREA ou no CAU
          </label>
          {form.hasRegistration && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={field("council")}>Conselho</Label>
                <select id={field("council")} className={SELECT} value={form.council} onChange={(e) => update("council", e.target.value as "CREA" | "CAU")}>
                  <option value="CREA">CREA</option>
                  <option value="CAU">CAU</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={field("regnumber")}>Número</Label>
                <Input id={field("regnumber")} required value={form.registrationNumber} onChange={(e) => update("registrationNumber", e.target.value)} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={field("regstate")}>UF</Label>
                <Input id={field("regstate")} maxLength={2} value={form.registrationState} onChange={(e) => update("registrationState", e.target.value.toUpperCase())} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={field("regvalid")}>Validade da certidão</Label>
                <Input id={field("regvalid")} type="date" value={form.registrationValidUntil} onChange={(e) => update("registrationValidUntil", e.target.value)} />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Certidões</h2>
          </CardTitle>
          <CardDescription>Informe a validade das que a empresa já tem; deixe em branco as demais.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {CERTIFICATES.map((c) => (
            <div key={c.kind} className="flex flex-col gap-1.5">
              <Label htmlFor={field(`cert-${c.kind}`)}>{c.label}</Label>
              <Input
                id={field(`cert-${c.kind}`)}
                type="date"
                value={form.certificates[c.kind]}
                onChange={(e) => update("certificates", { ...form.certificates, [c.kind]: e.target.value })}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>Atestados técnicos</h2>
          </CardTitle>
          <CardDescription>
            Para cada atestado, descreva a obra e liste os serviços com quantidade e unidade, como
            constam no documento. As quantidades são somadas e comparadas com o mínimo do edital.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {form.attestations.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum atestado cadastrado.</p>
          )}
          {form.attestations.map((attestation, index) => (
            <fieldset key={index} className="flex flex-col gap-3 rounded-lg border p-3">
              <legend className="px-1 text-sm font-medium">Atestado {index + 1}</legend>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={field(`att-${index}-desc`)}>Obra ou serviço</Label>
                  <Input id={field(`att-${index}-desc`)} required minLength={3} value={attestation.description} onChange={(e) => updateAttestation(index, { description: e.target.value })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={field(`att-${index}-issuer`)}>Emitido por</Label>
                  <Input id={field(`att-${index}-issuer`)} value={attestation.issuer} onChange={(e) => updateAttestation(index, { issuer: e.target.value })} />
                </div>
              </div>
              {attestation.quantities.map((quantity, qi) => (
                <div key={qi} className="grid grid-cols-[1fr_6rem_5rem_auto] items-end gap-2">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={field(`att-${index}-${qi}-svc`)}>Serviço</Label>
                    <Input
                      id={field(`att-${index}-${qi}-svc`)}
                      required
                      minLength={3}
                      value={quantity.service}
                      onChange={(e) => updateAttestation(index, { quantities: attestation.quantities.map((q, j) => (j === qi ? { ...q, service: e.target.value } : q)) })}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={field(`att-${index}-${qi}-qty`)}>Quantidade</Label>
                    <Input
                      id={field(`att-${index}-${qi}-qty`)}
                      required
                      inputMode="decimal"
                      value={quantity.quantity}
                      onChange={(e) => updateAttestation(index, { quantities: attestation.quantities.map((q, j) => (j === qi ? { ...q, quantity: e.target.value } : q)) })}
                    />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={field(`att-${index}-${qi}-unit`)}>Unidade</Label>
                    <select
                      id={field(`att-${index}-${qi}-unit`)}
                      className={SELECT}
                      value={quantity.unit}
                      onChange={(e) => updateAttestation(index, { quantities: attestation.quantities.map((q, j) => (j === qi ? { ...q, unit: e.target.value as QuantityUnit } : q)) })}
                    >
                      {UNITS.map((u) => (
                        <option key={u.value} value={u.value}>{u.label}</option>
                      ))}
                    </select>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remover o serviço ${qi + 1} do atestado ${index + 1}`}
                    onClick={() => updateAttestation(index, { quantities: attestation.quantities.filter((_, j) => j !== qi) })}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => updateAttestation(index, { quantities: [...attestation.quantities, { service: "", quantity: "", unit: "m2" }] })}
                >
                  <Plus aria-hidden /> Serviço
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => update("attestations", form.attestations.filter((_, i) => i !== index))}
                >
                  <Trash2 aria-hidden /> Remover atestado
                </Button>
              </div>
            </fieldset>
          ))}
          <Button
            type="button"
            variant="outline"
            className="self-start"
            onClick={() =>
              update("attestations", [
                ...form.attestations,
                { description: "", issuer: "", quantities: [{ service: "", quantity: "", unit: "m2" }] },
              ])
            }
          >
            <Plus aria-hidden /> Adicionar atestado
          </Button>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="lg" disabled={saving}>
          {saving ? "Salvando…" : "Salvar perfil"}
        </Button>
        <Button type="button" size="lg" variant="outline" onClick={() => router.push("/perfis")}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}
