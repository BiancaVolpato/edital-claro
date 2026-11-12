import { Suspense } from "react";

import { EligibilityView } from "@/components/eligibility-view";

export default function EligibilityPage({ params }: PageProps<"/analises/[id]/aptidao">) {
  return (
    <Suspense fallback={<p role="status" className="p-10">Carregando…</p>}>
      <EligibilityView params={params} />
    </Suspense>
  );
}
