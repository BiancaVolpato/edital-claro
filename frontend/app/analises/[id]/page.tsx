import { Suspense } from "react";

import { AnalysisView } from "@/components/analysis-view";

export default function AnalysisPage({ params }: PageProps<"/analises/[id]">) {
  return (
    <Suspense fallback={<p role="status" className="p-10">Carregando análise…</p>}>
      <AnalysisView params={params} />
    </Suspense>
  );
}
