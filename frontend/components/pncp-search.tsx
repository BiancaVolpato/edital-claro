"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useIsClient } from "@/lib/browser";
import { api, postJson } from "@/lib/client";
import { brDate, brl } from "@/lib/format";
import type { PncpImportResponse, PncpSearchResponse, Procurement } from "@/lib/types";

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  // Local date (toISOString would shift it to UTC).
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function PncpSearch() {
  const router = useRouter();
  const ids = { from: useId(), to: useId(), uf: useId(), city: useId(), q: useId() };
  // The default period (last 15 days) depends on today's date, so it is only
  // filled in the browser; the prerendered page has empty dates.
  const isClient = useIsClient();
  const [fromInput, setFrom] = useState<string | null>(null);
  const [toInput, setTo] = useState<string | null>(null);
  const from = fromInput ?? (isClient ? daysAgo(15) : "");
  const to = toInput ?? (isClient ? daysAgo(0) : "");
  const [uf, setUf] = useState("SC");
  const [city, setCity] = useState("");
  const [q, setQ] = useState("pavimentação");
  const [searching, setSearching] = useState(false);
  const [importing, setImporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<PncpSearchResponse | null>(null);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    setSearching(true);
    setError(null);
    setResponse(null);
    const params = new URLSearchParams({ data_inicial: from, data_final: to });
    if (uf.trim()) params.set("uf", uf.trim());
    if (city.trim()) params.set("municipio", city.trim());
    if (q.trim()) params.set("q", q.trim());
    try {
      setResponse(await api<PncpSearchResponse>(`/pncp/search?${params}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha na busca.");
    } finally {
      setSearching(false);
    }
  }

  async function importEdital(procurement: Procurement) {
    setImporting(procurement.control_number);
    setError(null);
    try {
      const result = await postJson<PncpImportResponse>("/pncp/import", {
        numero_controle: procurement.control_number,
      });
      router.push(`/documentos/${result.documents[0].document.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao importar.");
      setImporting(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={search} className="grid grid-cols-2 gap-3 sm:grid-cols-6">
        <div className="col-span-1 flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor={ids.from}>Publicado de</Label>
          <Input id={ids.from} type="date" required value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="col-span-1 flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor={ids.to}>até</Label>
          <Input id={ids.to} type="date" required value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor={ids.uf}>UF</Label>
          <Input id={ids.uf} maxLength={2} value={uf} onChange={(e) => setUf(e.target.value.toUpperCase())} />
        </div>
        <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-3">
          <Label htmlFor={ids.city}>Município (opcional)</Label>
          <Input id={ids.city} value={city} onChange={(e) => setCity(e.target.value)} />
        </div>
        <div className="col-span-2 flex flex-col gap-1.5 sm:col-span-3">
          <Label htmlFor={ids.q}>Palavras no objeto</Label>
          <Input
            id={ids.q}
            value={q}
            placeholder="ex.: pavimentação, reforma, escola"
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <Button type="submit" className="col-span-2 sm:col-span-6" size="lg" disabled={searching || !from || !to}>
          {searching ? "Buscando no PNCP…" : "Buscar no PNCP"}
        </Button>
      </form>

      {searching && (
        <p role="status" className="text-sm text-muted-foreground">
          A busca lê as páginas do período no PNCP e pode levar até um minuto quando o portal está lento.
        </p>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {response && (
        <section aria-live="polite" className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            {response.total_matches === 0
              ? `Nenhuma contratação encontrada entre ${response.scanned} lidas. Tente outro período ou outras palavras.`
              : `${response.total_matches} contratação(ões) encontrada(s) entre ${response.scanned} lidas.`}
          </p>
          {response.warnings.map((warning) => (
            <Alert key={warning}>
              <AlertDescription>{warning}</AlertDescription>
            </Alert>
          ))}
          <ul className="flex flex-col gap-2">
            {response.results.map((p) => (
              <li key={p.control_number} className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="text-sm font-medium">{p.object}</p>
                  <p className="text-xs text-muted-foreground">
                    {[p.municipality && `${p.municipality}/${p.uf}`, p.modality_name, p.estimated_value ? brl(p.estimated_value) : null, p.published_at && `publicado em ${brDate(p.published_at)}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <p className="font-mono text-xs text-muted-foreground">{p.control_number}</p>
                </div>
                <Button
                  variant="outline"
                  onClick={() => importEdital(p)}
                  disabled={importing !== null}
                  aria-label={`Importar o edital: ${p.object}`}
                >
                  {importing === p.control_number ? "Importando…" : "Importar edital"}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
