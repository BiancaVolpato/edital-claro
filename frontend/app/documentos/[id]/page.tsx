import { Suspense } from "react";

import { DocumentView } from "@/components/document-view";
import { Skeleton } from "@/components/ui/skeleton";

export default function DocumentPage({ params }: PageProps<"/documentos/[id]">) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-10">
      <Suspense fallback={<Skeleton className="h-40" />}>
        <DocumentView params={params} />
      </Suspense>
    </main>
  );
}
