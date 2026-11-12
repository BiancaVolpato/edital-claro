import Link from "next/link";
import { Suspense } from "react";

import { CurrentNavLinks, NavLinks } from "@/components/nav-links";

export function SiteHeader() {
  return (
    <header className="border-b bg-background print:hidden">
      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Edital Claro
        </Link>
        <nav aria-label="Principal">
          {/* The current page is only known at request time; the links render without
              the highlight until then. */}
          <Suspense fallback={<NavLinks pathname={null} />}>
            <CurrentNavLinks />
          </Suspense>
        </nav>
      </div>
    </header>
  );
}
