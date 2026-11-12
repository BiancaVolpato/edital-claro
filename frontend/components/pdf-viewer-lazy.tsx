"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

// PDF.js needs the browser: never render the viewer on the server.
export const PdfViewerLazy = dynamic(() => import("@/components/pdf-viewer"), {
  ssr: false,
  loading: () => <Skeleton className="h-full min-h-96 w-full" />,
});
