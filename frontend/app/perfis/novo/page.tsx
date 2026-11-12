import type { Metadata } from "next";

import { ProfileForm } from "@/components/profile-form";

export const metadata: Metadata = { title: "Novo perfil · Edital Claro" };

export default function NewProfilePage() {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">Novo perfil de empresa</h1>
      <ProfileForm />
    </main>
  );
}
