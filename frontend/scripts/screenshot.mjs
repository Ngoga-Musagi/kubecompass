// Visual audit helper: captures pages at desktop and mobile widths.
// Usage: node scripts/screenshot.mjs [--guest <uuid>] [--out ../.cache/screens] [path ...]
// Requires the stack to be running (frontend :3000, backend :8000).
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  if (i === -1) return dflt;
  const v = args[i + 1];
  args.splice(i, 2);
  return v;
};
const guest = opt("--guest", null);
const out = path.resolve(opt("--out", "../.cache/screens"));
const base = opt("--base", "http://localhost:3000");
const dark = args.includes("--dark") ? (args.splice(args.indexOf("--dark"), 1), true) : false;
const fold = args.includes("--fold") ? (args.splice(args.indexOf("--fold"), 1), true) : false;
const mobileOnly = args.includes("--mobile") ? (args.splice(args.indexOf("--mobile"), 1), true) : false;
const pages = args.length ? args : ["/"];
mkdirSync(out, { recursive: true });

const viewports = mobileOnly
  ? [{ name: "mobile", width: 390, height: 844 }]
  : [
      { name: "desktop", width: 1440, height: 960 },
      { name: "mobile", width: 390, height: 844 },
    ];

const browser = await chromium.launch();
for (const vp of viewports) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 1 });
  await ctx.addInitScript(
    ([g, d]) => {
      if (g) localStorage.setItem("kubecompass.guest-id", g);
      localStorage.setItem("kubecompass.theme", d ? "dark" : "light");
    },
    [guest, dark],
  );
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  for (const p of pages) {
    await page.goto(base + p, { waitUntil: "networkidle", timeout: 90_000 });
    await page.waitForTimeout(800);
    const file = path.join(out, `${vp.name}${dark ? "-dark" : ""}-${p.replace(/[^a-z0-9]+/gi, "_") || "home"}.png`);
    await page.screenshot({ path: file, fullPage: !fold });
    const overflow = await page.evaluate(() => {
      const w = window.innerWidth;
      if (document.documentElement.scrollWidth <= w) return null;
      const bad = [...document.querySelectorAll("body *")].filter((el) => el.getBoundingClientRect().right > w + 1);
      return bad.slice(-4).map((el) => `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)}`).join(" | ");
    });
    console.log(`${file}${overflow ? `  [horizontal overflow: ${overflow}]` : ""}`);
  }
  if (errors.length) console.log(`console errors (${vp.name}):\n  ` + errors.slice(0, 8).join("\n  "));
  await ctx.close();
}
await browser.close();
