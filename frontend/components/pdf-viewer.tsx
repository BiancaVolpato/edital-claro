"use client";

// PDF viewer that opens on the cited page and highlights the quoted text.
// Loaded only in the browser (see pdf-viewer-lazy.tsx): PDF.js needs the DOM.

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { Button } from "@/components/ui/button";

// Must be set in the same module that renders <Document> (react-pdf docs).
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export type PdfTarget = { page: number; quote: string | null; key: number };

// PDF.js text content mixes text items (with `str`) and marked-content markers.
type TextItemLike = object;

function itemText(item: TextItemLike): string {
  return "str" in item && typeof item.str === "string" ? item.str : "";
}

/** Lowercase letters and digits only: PDF.js and the backend split and space text
 *  differently, so matching ignores spaces, punctuation, accents and hyphenation. */
function squash(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

/** Indexes of the text items that contain the quote (or its start or end). */
export function findQuoteItems(items: readonly TextItemLike[], quote: string): Set<number> {
  const bounds: { start: number; end: number }[] = [];
  let text = "";
  for (const item of items) {
    const piece = squash(itemText(item));
    bounds.push({ start: text.length, end: text.length + piece.length });
    text += piece;
  }
  const target = squash(quote);
  if (target.length < 8) return new Set();
  let start = text.indexOf(target);
  let length = target.length;
  if (start < 0) {
    // Long quotes may cross a line the viewer splits differently: try both ends.
    const head = target.slice(0, 60);
    const tail = target.slice(-60);
    start = text.indexOf(head);
    length = head.length;
    if (start < 0) {
      start = text.indexOf(tail);
      length = tail.length;
    }
  }
  if (start < 0) return new Set();
  const end = start + length;
  const found = new Set<number>();
  bounds.forEach((b, index) => {
    if (b.end > start && b.start < end && b.end > b.start) found.add(index);
  });
  return found;
}

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export default function PdfViewer({ url, target }: { url: string; target: PdfTarget | null }) {
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [zoom, setZoom] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(1);
  const [highlight, setHighlight] = useState<Set<number>>(new Set());
  const [notFound, setNotFound] = useState(false);

  // Fit the page to the column width.
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(280, Math.floor(entry.contentRect.width) - 2));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A new citation was chosen: go to its page (state adjusted while rendering,
  // as React recommends for state derived from a changed prop).
  const [seen, setSeen] = useState<number | null>(null);
  if (target && target.key !== seen) {
    setSeen(target.key);
    setPage(target.page);
    setHighlight(new Set());
    setNotFound(false);
  }

  const quote = target && target.page === page ? target.quote : null;

  const onText = useCallback(
    (content: { items: readonly TextItemLike[] }) => {
      if (!quote) {
        setHighlight(new Set());
        return;
      }
      const found = findQuoteItems(content.items, quote);
      setHighlight(found);
      setNotFound(found.size === 0);
    },
    [quote],
  );

  const renderText = useCallback(
    ({ str, itemIndex }: { str: string; itemIndex: number }) =>
      highlight.has(itemIndex) ? `<mark>${escapeHtml(str)}</mark>` : escapeHtml(str),
    [highlight],
  );

  const onTextLayer = useCallback(() => {
    container.current
      ?.querySelector(".react-pdf__Page__textContent mark")
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, []);

  const file = useMemo(() => url, [url]);

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2" role="toolbar" aria-label="Controles do PDF">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Página anterior">
            <ChevronLeft />
          </Button>
          <span className="min-w-28 text-center text-sm" aria-live="polite">
            Página {page} de {numPages || "…"}
          </span>
          <Button variant="outline" size="icon" onClick={() => setPage((p) => Math.min(numPages, p + 1))} disabled={!numPages || page >= numPages} aria-label="Próxima página">
            <ChevronRight />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))} aria-label="Diminuir zoom">
            <ZoomOut />
          </Button>
          <Button variant="outline" size="icon" onClick={() => setZoom((z) => Math.min(2.4, z + 0.2))} aria-label="Aumentar zoom">
            <ZoomIn />
          </Button>
        </div>
      </div>
      {quote && notFound && (
        <p className="text-xs text-muted-foreground" role="status">
          Não foi possível destacar o trecho nesta página do PDF; confira o texto da citação.
        </p>
      )}
      <div ref={container} className="min-h-0 flex-1 overflow-auto rounded-lg border bg-muted/40">
        <Document
          file={file}
          suspense={false}
          onLoadSuccess={(pdf) => setNumPages(pdf.numPages)}
          loading={<p className="p-4 text-sm" role="status">Carregando o PDF…</p>}
          error={<p className="p-4 text-sm text-destructive">Não foi possível abrir o PDF.</p>}
        >
          <Page
            key={`${page}-${quote ?? ""}`}
            pageNumber={page}
            width={Math.round(width * zoom)}
            suspense={false}
            customTextRenderer={renderText}
            onGetTextSuccess={onText}
            onRenderTextLayerSuccess={onTextLayer}
            loading={<p className="p-4 text-sm" role="status">Carregando a página…</p>}
          />
        </Document>
      </div>
    </div>
  );
}
