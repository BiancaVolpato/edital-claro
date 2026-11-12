"use client";

import { FileUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/client";
import { DEMO_ACTION_OFF, useDemo } from "@/lib/demo";
import type { DocumentDetail } from "@/lib/types";
import { cn } from "cn";

const MAX_MB = 50;

export function UploadCard() {
  const router = useRouter();
  const demo = useDemo();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function choose(selected: File | undefined) {
    setError(null);
    if (!selected) return;
    if (selected.type !== "application/pdf" && !selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Escolha um arquivo PDF.");
      return;
    }
    if (selected.size > MAX_MB * 1024 * 1024) {
      setError(`O arquivo passa do limite de ${MAX_MB} MB.`);
      return;
    }
    setFile(selected);
  }

  async function send() {
    if (!file) return;
    setSending(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const document = await api<DocumentDetail>("/documents", { method: "POST", body: form });
      router.push(`/documentos/${document.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha no envio.");
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <label
        htmlFor={inputId}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors hover:bg-muted/50 focus-within:ring-2 focus-within:ring-ring",
          dragging && "border-primary bg-muted",
        )}
      >
        <FileUp className="size-8 text-muted-foreground" aria-hidden />
        <span className="font-medium">
          {file ? file.name : "Arraste o PDF do edital ou clique para escolher"}
        </span>
        <span className="text-sm text-muted-foreground">
          {file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `PDF de até ${MAX_MB} MB`}
        </span>
        <input
          ref={input}
          id={inputId}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          onChange={(event) => choose(event.target.files?.[0])}
        />
      </label>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {demo && <p className="text-sm text-muted-foreground">{DEMO_ACTION_OFF}</p>}
      <Button onClick={send} disabled={demo || !file || sending} size="lg">
        {sending ? "Enviando…" : "Enviar edital"}
      </Button>
    </div>
  );
}
