"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { use, useState } from "react";
import useSWR from "swr";

import { ProfileForm } from "@/components/profile-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { api, fetcher } from "@/lib/client";
import { brl } from "@/lib/format";
import type { CompanyProfile } from "@/lib/types";

export function ProfileList() {
  const saved = useSearchParams().get("salvo");
  const { data, error, isLoading, mutate } = useSWR<CompanyProfile[]>("/profiles", fetcher);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function remove(profile: CompanyProfile) {
    if (!window.confirm(`Apagar o perfil "${profile.name}"? As verificações já feitas continuam guardadas.`)) return;
    setDeleteError(null);
    try {
      await api(`/profiles/${profile.id}`, { method: "DELETE" });
      await mutate();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Não foi possível apagar.");
    }
  }

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold">Perfis de empresa</h1>
          <p className="text-sm text-muted-foreground">
            O perfil reúne o que a empresa tem (atestados, certidões, capital) para comparar com as
            exigências de cada edital.
          </p>
        </div>
        <Link href="/perfis/novo" className={buttonVariants()}>
          <Plus aria-hidden /> Novo perfil
        </Link>
      </header>
      {saved && (
        <Alert role="status">
          <AlertDescription>Perfil salvo.</AlertDescription>
        </Alert>
      )}
      {deleteError && (
        <Alert variant="destructive">
          <AlertDescription>{deleteError}</AlertDescription>
        </Alert>
      )}
      {isLoading && <p role="status">Carregando perfis…</p>}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}
      {data && data.length === 0 && (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed p-6">
          <p className="text-sm text-muted-foreground">Nenhum perfil cadastrado ainda.</p>
          <Link href="/perfis/novo" className={buttonVariants({ variant: "outline" })}>
            Cadastrar o primeiro perfil
          </Link>
        </div>
      )}
      {data && data.length > 0 && (
        <ul className="flex flex-col divide-y rounded-lg border">
          {data.map((profile) => (
            <li key={profile.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="font-medium">{profile.name}</span>
                <span className="text-xs text-muted-foreground">
                  {[
                    profile.size,
                    `${profile.attestations.length} atestado(s)`,
                    `${profile.certificates.length} certidão(ões)`,
                    profile.net_worth !== null ? `PL ${brl(profile.net_worth)}` : null,
                    profile.registration ? `${profile.registration.council} ${profile.registration.number}` : "sem registro em conselho",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
              <div className="flex gap-2">
                <Link href={`/perfis/${profile.id}`} className={buttonVariants({ variant: "outline", size: "sm" })} aria-label={`Editar ${profile.name}`}>
                  <Pencil aria-hidden /> Editar
                </Link>
                <Button variant="ghost" size="sm" onClick={() => remove(profile)} aria-label={`Apagar ${profile.name}`}>
                  <Trash2 aria-hidden /> Apagar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function ProfileEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error } = useSWR<CompanyProfile>(`/profiles/${id}`, fetcher);
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    );
  }
  if (!data) return <p role="status">Carregando perfil…</p>;
  return <ProfileForm profile={data} />;
}
