"use client";

import useSWR from "swr";

import { fetcher } from "@/lib/client";

type Health = { status: "ok"; version: string; database: "ok" | "unavailable"; demo: boolean };

/** True on the public demo server, where uploads, imports and new analyses are off. */
export function useDemo(): boolean {
  const { data } = useSWR<Health>("/health", fetcher, { revalidateOnFocus: false });
  return data?.demo ?? false;
}

export const DEMO_ACTION_OFF =
  "Desativado na demonstração pública. Rode o projeto localmente para analisar outros editais.";
