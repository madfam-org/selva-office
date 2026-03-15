import { test, expect, openDashboard } from "./fixtures";

test.describe("Approval Flow", () => {
  test("dashboard shows task board", async ({ authedPage: page }) => {
    await openDashboard(page);

    // Verify kanban columns are visible
    const dashboard = page.locator(
      '[data-testid="dashboard-panel"], [class*="dashboard"]',
    );
    await expect(dashboard).toBeVisible({ timeout: 5000 });
  });
});
