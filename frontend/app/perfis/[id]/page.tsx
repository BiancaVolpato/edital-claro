import { Suspense } from "react";

import { ProfileEditor } from "@/components/profile-list";

export default function EditProfilePage({ params }: PageProps<"/perfis/[id]">) {
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10">
      <h1 className="text-2xl font-semibold">Editar perfil</h1>
      <Suspense fallback={<p role="status">Carregando perfil…</p>}>
        <ProfileEditor params={params} />
      </Suspense>
    </main>
  );
}
