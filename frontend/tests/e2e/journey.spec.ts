import { expect, test } from "@playwright/test";

// Demonstration scenario (docs/PRODUCT.md §Demo) against the real running stack and real data.
const INTENT =
  "I am building an AI-powered Kubernetes autoscaler. I want to understand production AI infrastructure, GPU scheduling, inference optimization, observability, agentic systems, and workload orchestration. I prefer advanced technical talks, demonstrations, and sessions with practical engineering insights.";

test.describe.configure({ mode: "serial" });

test("intent → profile → recommendations → exploration → agenda → conflict → ICS", async ({ page, isMobile }) => {
  // Fresh guest so the journey starts empty.
  await page.addInitScript(() => {
    if (!sessionStorage.getItem("e2e-init")) {
      localStorage.clear();
      sessionStorage.setItem("e2e-init", "1");
    }
  });

  // Step 1: intent
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("learn");
  await page.getByLabel("Describe what you want to learn").fill(INTENT);
  await page.getByRole("button", { name: /plan my conference/i }).click();

  // Step 2: editable profile
  const profile = page.getByRole("region", { name: /what concompass understood/i });
  // Intent parsing may call an LLM (a cold local model can take ~10–20 s to load).
  await expect(profile).toBeVisible({ timeout: 60_000 });
  await expect(profile.getByText("GPU Scheduling & Sharing")).toBeVisible();
  await expect(profile.getByRole("button", { name: /edit/i })).toBeVisible();

  // Steps 3–5: hybrid retrieval + graph expansion → explained, prioritized recommendations
  const must = page.getByRole("region", { name: "Must attend" });
  await expect(must.locator("article").first()).toBeVisible();
  await expect(must.getByText(/Covers your interests/).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Explore" })).toBeVisible();
  await expect(page.getByText(/retrieved with Elasticsearch hybrid search/)).toBeVisible();

  // Step 6: exploration: open a topic knowledge page from a recommendation chip
  const firstTitle = (await must.locator("article h3").first().innerText()).trim();
  const chip = must.locator("article").first().locator("a[href^='/topics/']").first();
  const concept = (await chip.innerText()).trim();
  await chip.click();
  await expect(page.getByRole("heading", { level: 1, name: concept })).toBeVisible();
  await expect(page.getByText(/sessions? ·/).first()).toBeVisible();
  await page.goBack();

  // Step 7: add sessions to the agenda
  await must.locator("article").first().getByRole("button", { name: /add to agenda/i }).click();
  await expect(page.getByText("Added to your agenda").or(page.getByText(/Added, with a time conflict/))).toBeVisible();

  // Step 8: create a conflict deliberately from search (two talks at the same time) and resolve it
  await page.goto("/search?q=GPU%20sharing&mode=hybrid&day=2026-11-10");
  const cards = page.locator("article");
  await expect(cards.first()).toBeVisible();
  await cards.nth(0).getByRole("button", { name: /add to agenda/i }).click();
  await cards.nth(1).getByRole("button", { name: /add to agenda/i }).click();

  await page.goto("/agenda");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Your week");
  await expect(page.getByText(/does not reserve a seat/)).toBeVisible();
  // The agenda shows one day at a time; the first recommendation may be on any day.
  const dayTabs = page.getByRole("tab");
  await expect(dayTabs.first()).toBeVisible();
  let found = false;
  for (let i = 0; i < (await dayTabs.count()) && !found; i++) {
    await dayTabs.nth(i).click();
    found = await page.getByText(firstTitle).first().isVisible();
  }
  expect(found, `"${firstTitle}" should be in the agenda`).toBe(true);

  const altButtons = page.getByRole("button", { name: /alternatives/i });
  if ((await altButtons.count()) > 0) {
    await altButtons.first().click();
    await expect(page.getByRole("dialog", { name: "Alternatives" })).toBeVisible();
    await page.keyboard.press("Escape");
  }

  // Step 9: calendar export
  if (!isMobile) {
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: /export \.ics/i }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/\.ics$/);
    const path = await file.path();
    const fs = await import("node:fs");
    const ics = fs.readFileSync(path!, "utf8");
    expect(ics).toContain("BEGIN:VCALENDAR");
    expect(ics).toContain("TZID=America/Denver");
  }
});

test("knowledge graph is interactive", async ({ page }) => {
  await page.goto("/graph?focus=topic%3Agpu-scheduling");
  await expect(page.getByRole("heading", { name: "Explore connections" })).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(page.getByText("Connections & evidence")).toBeVisible();
  await page.getByLabel("Find in graph").fill("ebpf");
  await page.getByRole("button", { name: /eBPF/ }).first().click();
  await expect(page.getByRole("heading", { name: "eBPF", level: 2 })).toBeVisible();
});

test("event agent: explicit permissions, grounded answers and confirmed actions", async ({ page }) => {
  await page.goto("/assistant"); // the old assistant route now leads to the agent
  await expect(page).toHaveURL(/\/agent$/);

  // 1. Off until the attendee enables it and chooses what it may do.
  await expect(page.getByRole("heading", { name: /Your companion for/ })).toBeVisible();
  await expect(page.getByLabel(/Read event information/)).toBeChecked();
  await expect(page.getByLabel(/Connect external accounts/)).toBeDisabled();
  await page.getByRole("button", { name: "Enable my agent" }).click();

  // 2. Grounded answers with sources, rendered as cards.
  await page.getByRole("button", { name: "Find something related to GPU scheduling" }).click();
  await expect(page.getByText(/From the official schedule|AI wording/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("main article a[href^='/sessions/']").first()).toBeVisible();

  // 3. It admits gaps instead of inventing sessions.
  const box = page.getByLabel("Message your agent");
  await box.fill("Are there sessions about medieval pottery glazing?");
  await box.press("Enter");
  await expect(page.getByText(/couldn't find sessions or speakers/i)).toBeVisible({ timeout: 60_000 });

  // 4. Agenda changes are proposed, and only happen when the attendee confirms.
  await box.fill("Add the session about GPU time-slicing to my agenda");
  await box.press("Enter");
  const confirm = page.getByRole("article", { name: "Confirm agenda change" });
  await expect(confirm).toBeVisible({ timeout: 60_000 });
  await confirm.getByRole("button", { name: /Yes, add it/ }).click();
  await expect(page.getByText("Added to your agenda.")).toBeVisible();

  // 5. Time-aware follow-up uses the saved agenda.
  await box.fill("Show my agenda");
  await box.press("Enter");
  await expect(page.getByText(/You have 1 session saved/)).toBeVisible({ timeout: 60_000 });

  // 6. The attendee can review and revoke permissions at any time.
  await page.getByRole("button", { name: "Agent permissions and memory" }).click();
  await expect(page.getByText("Recent actions you confirmed")).toBeVisible();
  await page.getByRole("button", { name: "Turn off agent" }).click();
  await expect(page.getByRole("button", { name: "Enable my agent" })).toBeVisible();
});
