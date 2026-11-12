"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "cn";

const LINKS = [
  { href: "/", label: "Início" },
  { href: "/perfis", label: "Perfis de empresa" },
  { href: "/sobre", label: "Sobre e limitações" },
];

export function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <ul className="flex flex-wrap gap-1 text-sm">
      {LINKS.map((link) => {
        const active =
          pathname !== null &&
          (link.href === "/" ? pathname === "/" : pathname.startsWith(link.href));
        return (
          <li key={link.href}>
            <Link
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "rounded-md px-3 py-1.5 transition-colors hover:bg-muted",
                active && "bg-muted font-medium",
              )}
            >
              {link.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function CurrentNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}
