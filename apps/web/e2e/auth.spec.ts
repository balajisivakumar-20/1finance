import { expect, test } from "@playwright/test";

test("rejects wrong password with a generic message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@1finance.app");
  await page.getByLabel("Password").fill("nope");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator("form [role=alert]")).toContainText("Incorrect email or password");
  expect(page.url()).not.toContain("password"); // credentials never end up in the URL
});

test("unauthenticated users are redirected to login", async ({ page }) => {
  await page.goto("/transactions");
  await expect(page).toHaveURL(/\/login/);
});
