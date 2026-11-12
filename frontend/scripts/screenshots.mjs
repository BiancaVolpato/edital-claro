// Captures the README screenshots from a running instance (the demo is best:
// it already has analyses). Uses a browser installed on the machine.
//
//   npm run screenshots -- [base URL]          default: http://localhost:3000
//
// Environment: BROWSER_CHANNEL (chrome, msedge; default chrome), OUT_DIR
// (default: docs/img in the repository).

import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

const base = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
const outDir = process.env.OUT_DIR ?? fileURLToPath(new URL("../../docs/img/", import.meta.url));
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL ?? "chrome" });
const page = await browser.newPage({ viewport: { width: 1360, height: 900 }, locale: "pt-BR" });
page.setDefaultTimeout(90_000); // a sleeping free-tier backend takes about a minute to wake

async function shot(name, options = {}) {
  const path = `${outDir}/${name}.png`;
  await page.screenshot({ path, ...options });
  console.log(`ok ${path}`);
}

await page.goto(`${base}/`);
await page.getByRole("heading", { name: "Análises recentes" }).waitFor();
await page.locator('a[href^="/analises/"]').first().waitFor();
await shot("01-inicio", { fullPage: true });

const analyses = await (await page.request.get(`${base}/api/analyses`)).json();
const analysis = analyses.find((a) => a.status === "completed");
if (!analysis) throw new Error("Nenhuma análise concluída nesta instância.");

await page.goto(`${base}/analises/${analysis.id}`);
await page.getByRole("tab", { name: "Campos" }).waitFor();
await shot("02-analise");

// A citation opens the PDF on its page with the quote highlighted.
await page.getByRole("button", { name: /^Ver no edital, página/ }).first().click();
await page.locator("mark").first().waitFor();
await page.waitForTimeout(500);
await shot("03-citacao");

await page.getByRole("tab", { name: "Riscos" }).click();
await page.waitForTimeout(500);
await shot("04-riscos");

await page.getByRole("tab", { name: "Checklist" }).click();
await page.waitForTimeout(500);
await shot("05-checklist");

await page.goto(`${base}/analises/${analysis.id}/aptidao`);
await page.locator('section[aria-labelledby="veredito"]').waitFor();
await shot("06-aptidao");

await browser.close();
