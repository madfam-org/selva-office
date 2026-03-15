import { test as base, expect, type Page } from "@playwright/test";

/**
 * Shared fixtures and helpers for E2E tests.
 * Assumes DEV_AUTH_BYPASS=true is set (dev login flow).
 */

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    // Dev auth bypass: navigate to login, fill display name, submit
    await page.goto("/");
    // Wait for either the game canvas or the login page
    const loginVisible = await page
      .locator('input[name="displayName"], input[placeholder*="name" i]')
      .isVisible({ timeout: 5000 })
      .catch(() => false);
    if (loginVisible) {
      await page.fill(
        'input[name="displayName"], input[placeholder*="name" i]',
        "E2E Tester",
      );
      await page.click('button[type="submit"]');
    }
    // Wait for the game to load (Phaser canvas or main content)
    await page.waitForSelector("canvas, [data-testid='office-main']", {
      timeout: 15000,
    });
    await use(page);
  },
});

export { expect };

export async function openDashboard(page: Page): Promise<void> {
  const dashBtn = page.locator(
    '[data-testid="dashboard-toggle"], button:has-text("Dashboard")',
  );
  if (await dashBtn.isVisible()) {
    await dashBtn.click();
    await page.waitForSelector(
      '[data-testid="dashboard-panel"], [class*="dashboard"]',
      { timeout: 5000 },
    );
  }
}

export async function waitForGameLoad(page: Page): Promise<void> {
  await page.waitForSelector("canvas", { timeout: 15000 });
  // Wait a bit for Phaser to initialize
  await page.waitForTimeout(2000);
}
