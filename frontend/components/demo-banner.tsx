"use client";

import { Info } from "lucide-react";
import Link from "next/link";

import { useDemo } from "@/lib/demo";

export function DemoBanner() {
  const demo = useDemo();
  if (!demo) return null;
  return (
    <div role="status" className="border-b bg-muted/60 print:hidden">
      <p className="mx-auto flex w-full max-w-7xl items-start gap-2 px-4 py-2 text-sm">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          <strong>Demonstração.</strong> Três editais já foram analisados pela IA (lista na página
          inicial), para você ver os resultados sem espera nem custo. Envio de PDF, importação do PNCP e novas
          análises estão desativados; perfis e verificações de aptidão funcionam (sem a IA).{" "}
          <Link href="/sobre" className="underline underline-offset-2">
            Saiba mais
          </Link>
          .
        </span>
      </p>
    </div>
  );
}
