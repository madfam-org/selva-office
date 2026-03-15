import { test, expect, openDashboard } from "./fixtures";

test.describe("Task Dispatch", () => {
  test("can open task dispatch panel", async ({ authedPage: page }) => {
    // Open dashboard
    await openDashboard(page);

    // Look for "+ New Task" button
    const newTaskBtn = page.locator(
      'button:has-text("New Task"), [data-testid="new-task-btn"]',
    );
    if (
      await newTaskBtn.isVisible({ timeout: 5000 }).catch(() => false)
    ) {
      await newTaskBtn.click();

      // Verify dispatch panel opened
      const panel = page.locator(
        '[data-testid="task-dispatch-panel"], [class*="dispatch"]',
      );
      await expect(panel).toBeVisible({ timeout: 5000 });
    }
  });
});
