import type { Metadata } from "next";
import { Suspense } from "react";

import { ProfileList } from "@/components/profile-list";

export const metadata: Metadata = { title: "Perfis de empresa · Edital Claro" };

export default function ProfilesPage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10">
      <Suspense fallback={<p role="status">Carregando perfis…</p>}>
        <ProfileList />
      </Suspense>
    </main>
  );
}
