import { expect, test as setup } from "@playwright/test";

setup("sign in once", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@1finance.app");
  await page.getByLabel("Password").fill("demo-1finance");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL("/");
  await page.context().storageState({ path: "e2e/.auth/state.json" });
});
