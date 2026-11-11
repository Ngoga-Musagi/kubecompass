import { expect, test, type Browser, type Page } from "@playwright/test";

// Personalization by email/username: same handle = same profile on any device; everyone else
// (other handles, anonymous visitors) starts fresh.
const INTENT = "I want to learn GPU scheduling and AI inference on Kubernetes.";

async function openMenuIfMobile(page: Page, isMobile: boolean) {
  if (isMobile) await page.getByRole("button", { name: "Open menu" }).click();
}

async function signIn(page: Page, isMobile: boolean, handle: string) {
  await openMenuIfMobile(page, isMobile);
  await page.getByRole("button", { name: "Add email or username" }).click();
  await page.getByLabel("Email or username").fill(handle);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
}

async function freshPage(browser: Browser, isMobile: boolean) {
  const ctx = await browser.newContext(isMobile ? { viewport: { width: 390, height: 844 }, isMobile: true } : {});
  return ctx.newPage();
}

test("profiles are separated per email/username", async ({ browser, isMobile }) => {
  test.setTimeout(120_000);
  const user = `e2e_${Date.now().toString(36)}`;

  // Person A on device 1: signs in with a username and builds a profile.
  const a1 = await freshPage(browser, isMobile);
  await a1.goto("/");
  await signIn(a1, isMobile, user);
  await expect(a1.getByText(user).first()).toBeAttached();
  await a1.getByLabel("Describe what you want to learn").fill(INTENT);
  await a1.getByRole("button", { name: /plan my conference/i }).click();
  await expect(a1.getByRole("region", { name: /what concompass understood/i })).toBeVisible({ timeout: 60_000 });

  // Person A on device 2: same username → same profile.
  const a2 = await freshPage(browser, isMobile);
  await a2.goto("/");
  await signIn(a2, isMobile, user.toUpperCase());
  await expect(a2.getByRole("region", { name: /what concompass understood/i })).toBeVisible({ timeout: 30_000 });

  // Someone else (different username) and an anonymous visitor start empty.
  const b = await freshPage(browser, isMobile);
  await b.goto("/");
  await expect(b.getByLabel("Describe what you want to learn")).toBeVisible();
  await expect(b.getByRole("region", { name: /what concompass understood/i })).toHaveCount(0);
  await signIn(b, isMobile, `${user}_other`);
  await expect(b.getByLabel("Describe what you want to learn")).toBeVisible();
  await expect(b.getByRole("region", { name: /what concompass understood/i })).toHaveCount(0);

  // Invalid handles are explained, not accepted.
  const c = await freshPage(browser, isMobile);
  await c.goto("/");
  await openMenuIfMobile(c, isMobile);
  await c.getByRole("button", { name: "Add email or username" }).click();
  await c.getByLabel("Email or username").fill("a b");
  await c.getByRole("button", { name: "Continue" }).click();
  await expect(c.getByRole("alert")).toContainText(/username|email/i);
});
