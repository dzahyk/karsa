import { expect, test, type Page } from "@playwright/test";

const OUT = "../docs/portfolio/screenshots";
const DESKTOP = { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1.25 }; // → 1600×1000
const MOBILE = { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true }; // → 780×1688

async function as(page: Page, username: string, path: string) {
  const r = await page.request.post("/api/v1/auth/demo-login", { data: { username } });
  expect(r.ok()).toBeTruthy();
  await page.goto(path);
  await settle(page);
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".skeleton")).toHaveCount(0);
  await page.addStyleTag({ content: ".toasts{display:none!important} *{caret-color:transparent!important}" });
  await page.mouse.move(0, 0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForTimeout(400);
}

async function shot(page: Page, name: string, scrollTo?: string) {
  if (scrollTo) {
    await page.locator(scrollTo).first().evaluate((el) => window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 76 }));
    await page.waitForTimeout(250);
  } else {
    await page.evaluate(() => window.scrollTo(0, 0));
  }
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

test.describe("desktop", () => {
  test.use(DESKTOP);

  test("sign-in", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await settle(page);
    await shot(page, "01-sign-in");
  });

  test("cases", async ({ page }) => {
    await as(page, "nadia", "/cases");
    await shot(page, "02-cases");
  });

  test("requirements & evidence", async ({ page }) => {
    await as(page, "nadia", "/cases/DCF-1042/requirements");
    await page.getByRole("button", { name: "Geography: show evidence" }).click();
    await page.waitForTimeout(300);
    await shot(page, "03-requirements-evidence");
    await shot(page, "03b-evidence-highlight", "text=Drafted by");
  });

  test("feasibility", async ({ page }) => {
    await as(page, "nadia", "/cases/DCF-1042/feasibility");
    await shot(page, "04-feasibility", ".stepper");
    await shot(page, "05-capacity-scenarios", "text=Capacity check");
  });

  test("approval review with diff", async ({ page }) => {
    await as(page, "arif", "/approvals/3");
    await shot(page, "06-approval-review");
  });

  test("dual approval", async ({ page }) => {
    await as(page, "arif", "/approvals/5");
    await shot(page, "07-dual-approval");
  });

  test("execution unknown outcome", async ({ page }) => {
    await as(page, "jordan", "/workflows/EX-0082");
    await shot(page, "08-execution-unknown-outcome");
  });

  test("exception queue", async ({ page }) => {
    await as(page, "jordan", "/workflows");
    await shot(page, "09-exception-queue");
  });

  test("evaluation lab", async ({ page }) => {
    await as(page, "priya", "/evaluation");
    await shot(page, "10-evaluation-gate", "[aria-label='Split']");
    await page.getByRole("button", { name: /Dev \(24\)/ }).click();
    await page.waitForTimeout(300);
    await shot(page, "11-evaluation-dev", "[aria-label='Split']");
  });

  test("impact", async ({ page }) => {
    await as(page, "dewi", "/impact");
    await shot(page, "12-impact");
  });

  test("manage", async ({ page }) => {
    await as(page, "bima", "/manage");
    await shot(page, "13-manage-rate-cards");
    await page.getByRole("tab", { name: "Integrations" }).click();
    await page.waitForLoadState("networkidle");
    await shot(page, "14-manage-integrations");
  });

  test("audit", async ({ page }) => {
    await as(page, "lia", "/audit");
    await shot(page, "15-audit-log");
  });
});

test.describe("mobile", () => {
  test.use(MOBILE);

  test("mobile approval", async ({ page }) => {
    await as(page, "sari", "/approvals/5");
    await shot(page, "16-mobile-approval");
  });

  test("mobile cases", async ({ page }) => {
    await as(page, "nadia", "/cases");
    await shot(page, "17-mobile-cases");
  });
});
