import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SiteHeader } from "@/components/site-header";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Edital Claro",
  description: "Análise de editais de obras públicas com IA, com citação da página e do trecho de origem.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* Browser extensions add attributes to <body> before React loads (e.g.
          ColorZilla's cz-shortcut-listen). That is not an application error, so
          the mismatch warning is silenced for this element's own attributes only. */}
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
        <a
          href="#conteudo"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:ring-2 focus:ring-ring"
        >
          Pular para o conteúdo
        </a>
        <SiteHeader />
        <div id="conteudo" className="flex flex-1 flex-col">
          {children}
        </div>
      </body>
    </html>
  );
}
