import { expect, test, type Page } from "@playwright/test";
import { signIn } from "./helpers";

const BRIEF = `Subject: B2B lead campaign request — Aster Labs (synthetic)

Target: 3,000 qualified leads
Budget: Rp150,000,000 for the full campaign
Timeline: 2 months from campaign kickoff
Target segment: SaaS and fintech companies with 50–500 employees
Geography: to be determined
Reporting: weekly dashboard and sync of accepted leads to our CRM`;

async function confirm(page: Page, label: string) {
  await page.getByRole("button", { name: `${label}: show evidence` }).click();
  await page.getByRole("button", { name: "Confirm value" }).click();
  await expect(page.getByRole("status")).toContainText("Requirement confirmed");
}

test("intake → requirements → clarification → pricing → package → approval → authorization → async sandbox run", async ({ page }) => {
  await signIn(page, "nadia", "/cases");

  // 1. Intake
  await page.getByRole("button", { name: "New request" }).click();
  await page.getByLabel("Request title").fill("B2B Lead Campaign (E2E)");
  await page.getByLabel("Client (pseudonym)").fill("Aster Labs");
  await page.getByLabel("Client brief").fill(BRIEF);
  await page.getByRole("button", { name: "Create case" }).click();
  await expect(page).toHaveURL(/\/cases\/DCF-\d+\/requirements/);
  const code = page.url().match(/DCF-\d+/)![0];

  // 2. Review AI-drafted requirements against evidence
  await confirm(page, "Target (qualified leads)");
  await confirm(page, "Budget / proposed fee");
  await confirm(page, "Timeline");

  // Package is blocked while lead definition + geography are missing
  await page.getByRole("link", { name: "Feasibility & pricing" }).click();
  await expect(page.getByText("Clarification required before approval")).toBeVisible();
  await expect(page.getByRole("cell", { name: "Rp117,000,000" }).first()).toBeVisible();
  await expect(page.getByRole("cell", { name: "22.00%" }).first()).toBeVisible();
  await expect(page.getByText("375", { exact: true })).toBeVisible(); // capacity: leads per week
  await expect(page.getByRole("button", { name: "Create decision package" })).toBeDisabled();

  // 3. Clarification with a checkable reference and the client's own words
  await page.getByRole("link", { name: "Requirements & evidence" }).click();
  await page.getByRole("button", { name: "Generate for open items" }).click();
  await expect(page.getByRole("button", { name: "Record answer" })).toHaveCount(2);
  const answers = [
    "A qualified lead is a manager or above at a SaaS or fintech company with 50–500 staff who agrees to a discovery call.",
    "Indonesia — Jabodetabek and Surabaya.",
  ];
  for (const answer of answers) {
    await page.getByRole("button", { name: "Record answer" }).first().click();
    await page.getByLabel("Answer (as given)").fill(answer);
    await page.getByLabel("Answered by").fill("Maya Santoso (client)");
    await page.getByLabel("Reference someone else can check").fill("Email 'Re: lead criteria', 11 Nov 2026");
    await page.getByLabel(/Client's own words/).fill(answer);
    await page.getByRole("button", { name: "Save answer" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  }

  // 4. Feasibility (deterministic, server-side)
  await page.getByRole("link", { name: "Feasibility & pricing" }).click();
  await expect(page.getByText("Ready for a decision package")).toBeVisible();
  await page.getByRole("button", { name: "Save calculation" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();

  // 5. Decision package
  await page.getByRole("button", { name: "Create decision package" }).click();
  await expect(page).toHaveURL(/\/approvals\/\d+/);
  await expect(page.getByText("0 critical unresolved issues")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve decision" })).toHaveCount(0); // analysts cannot decide
  const reviewUrl = page.url();

  // 6. Human approval (Commercial Manager)
  await signIn(page, "arif", reviewUrl);
  await expect(page.getByText("Pending your approval")).toBeVisible();
  await page.locator(".action-bar").getByRole("button", { name: "Approve decision" }).click();
  const dlg = page.getByRole("dialog", { name: "Approve this decision?" });
  await dlg.getByRole("button", { name: "Approve decision" }).click();
  await expect(page.getByRole("status")).toContainText("Execution still needs authorization");
  await expect(page.getByText("Not yet authorized.")).toBeVisible();

  // 7. Separate execution authorization
  await page.getByRole("button", { name: "Authorize execution" }).click();
  const auth = page.getByRole("dialog", { name: "Authorize execution" });
  const submit = auth.getByRole("button", { name: "Authorize these actions" });
  await expect(submit).toBeDisabled();
  for (const box of await auth.getByRole("checkbox").all()) await box.check();
  await submit.click();
  await expect(page.getByRole("status")).toContainText("Execution authorized");

  // 8. Async sandbox run through the outbox worker, with an idempotent retry
  await signIn(page, "jordan", reviewUrl);
  await page.getByLabel("Failure injection (demo)").selectOption("tracker_timeout_before_commit");
  await page.getByRole("button", { name: "Run sandbox workflow" }).click();
  await expect(page).toHaveURL(/\/workflows\/EX-\d+/);
  await expect(page.getByText("Not completed")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Review and retry" }).click();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/2 of 2 sandbox records read back/).first()).toBeVisible();

  // The audit trail shows approval and execution as separate events
  await page.goto(`/cases/${code}/activity`);
  await expect(page.getByText(/Package v1 approved by Arif Wicaksono/)).toBeVisible();
  await expect(page.getByText(/authorized 2 sandbox action/)).toBeVisible();
});

test("password sign-in, role-based navigation and tenant isolation", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("priya");
  await page.getByLabel("Password").fill("decisionflow-demo");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/evaluation/);
  const nav = page.getByRole("navigation", { name: "Primary", exact: true });
  await expect(nav.getByRole("link")).toHaveText(["Evaluation"]);
  await page.goto("/cases");
  await expect(page.getByRole("heading", { name: "Not available for your role" })).toBeVisible();

  await signIn(page, "omar", "/cases");
  await expect(page.getByRole("link", { name: "DCF-2001" })).toBeVisible();
  await expect(page.getByRole("link", { name: "DCF-1042" })).toHaveCount(0);
  await page.goto("/cases/DCF-1042");
  await expect(page.getByText("Case DCF-1042 was not found.")).toBeVisible();
});
