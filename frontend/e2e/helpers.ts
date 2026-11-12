import { expect, type Page } from "@playwright/test";

/** Sign in as a synthetic demo account (DEMO_MODE) — same session cookie + CSRF flow as the UI. */
export async function signIn(page: Page, username: string, path = "/") {
  const r = await page.request.post("/api/v1/auth/demo-login", { data: { username } });
  expect(r.ok()).toBeTruthy();
  await page.goto(path);
}
