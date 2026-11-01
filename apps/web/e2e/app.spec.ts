import { expect, test, type Page } from "@playwright/test";


async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByText("Total net worth")).toBeVisible();
}

test("dashboard loads with net worth and demo labelling @responsive", async ({ page }) => {
  await login(page);
  await expect(page.getByText("Here's your financial overview.")).toBeVisible();
  await expect(page.getByText("Total net worth")).toBeVisible();
  await expect(page.getByText("Demo data").first()).toBeVisible();
  await expect(page.getByText("Asset allocation")).toBeVisible();
  await expect(page.getByText("Recent transactions")).toBeVisible();
});

test("range switch and currency switch update the dashboard", async ({ page }) => {
  await login(page);
  await page.getByRole("radiogroup", { name: "Net worth range" }).getByRole("radio", { name: "1Y" }).click();
  await expect(page.getByText("past year")).toBeVisible();
  await page.getByRole("button", { name: /Reporting currency/ }).click();
  await page.getByRole("menuitemradio", { name: "INR" }).click();
  await expect(page.getByText(/₹/).first()).toBeVisible();
});

test("theme switching applies the dark class", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Theme" }).first().click();
  await page.getByRole("menuitemradio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
});

test("transactions: search, open detail, recategorize", async ({ page }) => {
  await login(page);
  await page.goto("/transactions");
  await page.getByLabel("Search transactions").fill("tesco");
  const firstRow = page.locator("tbody tr").first();
  await expect(firstRow).toContainText(/Tesco/i);
  await firstRow.click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("Original description")).toBeVisible();
  const select = drawer.getByLabel("Category");
  const current = await select.evaluate((el: HTMLSelectElement) => el.selectedOptions[0]?.text);
  await select.selectOption({ label: current === "Household" ? "Groceries" : "Household" });
  await drawer.getByText("Apply this category to future transactions").click();
  await drawer.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Transaction updated")).toBeVisible();
});

test("budget creation", async ({ page }) => {
  await login(page);
  // idempotent: remove an existing Coffee budget first
  const csrf = (await page.context().cookies()).find((c) => c.name.endsWith("1f_csrf"))?.value ?? "";
  const res = await page.request.get("/api/v1/budgets");
  for (const b of (await res.json()).items) {
    if (b.category.slug === "coffee") await page.request.delete(`/api/v1/budgets/${b.id}`, { headers: { "X-CSRF-Token": csrf } });
  }
  await page.goto("/budgets");
  await page.getByRole("button", { name: "New budget" }).click();
  await page.getByLabel("Category").selectOption({ label: "Coffee" });
  await page.getByLabel(/Monthly amount/).fill("45");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Budget saved")).toBeVisible();
});

test("manual account creation via wizard", async ({ page }) => {
  await login(page);
  await page.goto("/accounts");
  await page.getByRole("button", { name: "Add account" }).first().click();
  await page.getByRole("button", { name: /Other institution/ }).click();
  await page.getByRole("button", { name: /Manual account/ }).click();
  await page.getByLabel("Account name").fill("E2E Wallet");
  await page.getByLabel("Current balance").fill("250");
  await page.getByRole("button", { name: "Add account" }).last().click();
  await expect(page.getByText("Manual account added")).toBeVisible();
});

test("real connector requires valid credentials (never fakes success)", async ({ page }) => {
  await login(page);
  await page.goto("/accounts?add=1");
  await page.getByRole("button", { name: /Interactive Brokers/ }).click();
  await page.getByRole("button", { name: /Official API/ }).click();
  await page.getByLabel("Flex Web Service token").fill("invalid");
  await page.getByLabel("Activity Flex Query ID").fill("1");
  await page.getByRole("button", { name: /Verify/ }).click();
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: /Authorization failed|Could not reach|IBKR Flex/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/connected$/)).toHaveCount(0);
});

test("statement import shows a validation preview before committing", async ({ page }) => {
  await login(page);
  await page.goto("/accounts");
  await page.getByRole("button", { name: /Actions for Revolut Current/ }).click();
  await page.getByRole("menuitem", { name: "Import statement" }).click();
  await page.locator('input[type=file]').setInputFiles({
    name: "statement.csv", mimeType: "text/csv",
    buffer: Buffer.from(`date,description,amount,currency\n2026-01-03,E2E Coffee ${Date.now()},-3.20,EUR\n2026-01-04,E2E Bakery ${Date.now()},-5.10,EUR\n`),
  });
  await expect(page.getByText("Valid rows")).toBeVisible();
  await page.getByRole("button", { name: /Import \d+ transactions/ }).click();
  await expect(page.getByText(/Imported \d+ transactions/)).toBeVisible();
});

test("report generation downloads a PDF", async ({ page }) => {
  await login(page);
  await page.goto("/reports");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "PDF" }).first().click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
});

test("command menu opens with keyboard shortcut", async ({ page }) => {
  await login(page);
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder(/Search transactions, merchants/).fill("spotify");
  await expect(page.getByRole("option").first()).toBeVisible();
});

test("bottom navigation on mobile @responsive", async ({ page, isMobile }) => {
  test.skip(!isMobile, "mobile only");
  await login(page);
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Transactions" }).click();
  await expect(page).toHaveURL("/transactions");
});
