import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

const PAGES: [string, string][] = [
  ["nadia", "/cases"], ["nadia", "/cases/DCF-1042/requirements"], ["nadia", "/cases/DCF-1042/feasibility"],
  ["arif", "/approvals"], ["arif", "/approvals/5"], ["jordan", "/workflows"], ["jordan", "/workflows/EX-0084"],
  ["priya", "/evaluation"], ["dewi", "/impact"], ["lia", "/audit"], ["bima", "/manage"],
];

async function noSerious(page: import("@playwright/test").Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".skeleton")).toHaveCount(0);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")}`)).toEqual([]);
}

test("no serious accessibility violations on the sign-in page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await noSerious(page);
});

for (const [user, path] of PAGES) {
  test(`no serious accessibility violations on ${path} (${user})`, async ({ page }) => {
    await signIn(page, user, path);
    await noSerious(page);
  });
}

test("mobile second approver completes a high-risk dual approval", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "sari", "/approvals");
  await page.getByRole("link", { name: /Crestview Retail/ }).first().click();
  await expect(page.getByText("High risk").first()).toBeVisible();
  await expect(page.getByText("1 of 2 approvals recorded")).toBeVisible();
  const bar = page.locator(".sticky-actions");
  const approve = bar.getByRole("button", { name: /Approve \(2 of 2\)/ });
  expect((await approve.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await approve.click();
  const dlg = page.getByRole("dialog", { name: "Approve this decision?" });
  const confirm = dlg.getByRole("button", { name: "Approve decision" });
  await expect(confirm).toBeDisabled(); // high risk → exception note required
  await dlg.getByLabel(/Reviewer note/).fill("Finance agrees to the one-off exception.");
  await confirm.click();
  await expect(page.getByRole("status")).toContainText("Decision approved");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});

test("keyboard-only approver can open a package, compare changes and reject it (AC-10)", async ({ page }) => {
  await signIn(page, "arif", "/approvals");
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.getByRole("link", { name: /Northbridge Health/ }).first().focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /Changes since previous version \(v1 → v2\)/ })).toBeVisible();
  const reject = page.locator(".action-bar").getByRole("button", { name: "Reject" });
  await reject.focus();
  await page.keyboard.press("Enter");
  const dlg = page.getByRole("dialog", { name: "Reject this proposal?" });
  await expect(dlg).toBeVisible();
  expect(await dlg.evaluate((d) => d.contains(document.activeElement))).toBeTruthy(); // focus moved into the dialog
  await page.keyboard.press("Escape");
  await expect(dlg).toHaveCount(0);
  await expect(reject).toBeFocused(); // focus returns to the opener
  await page.keyboard.press("Enter");
  await page.getByLabel(/Reviewer note/).focus();
  await page.keyboard.type("Hospital budget not yet signed off; resubmit after procurement review.");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("dialog").getByRole("button", { name: "Reject proposal" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("Proposal rejected");
});
