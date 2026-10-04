import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Statistics and Reports section visibility verification (M03_BS_029)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto("https://pt-dev.appevolve.intuitive.ai/");
    await page.locator("button:has-text('SSO Login')").click();
    await page.waitForTimeout(4000);
    await page.locator("#username").fill(process.env.APPEVOLVE_AUTOMATION_DEV_USERNAME ?? "");
    await page.locator("#password").fill(process.env.APPEVOLVE_AUTOMATION_DEV_PASSWORD ?? "");
    await page.locator("#kc-login").click();
    await page.waitForTimeout(2000);
    await page.locator("button.joyride__hurray-btn").click();
    await page.waitForTimeout(1000);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — Statistics and Reports section is visible with correct title and accessible content', async () => {
    await page.goto(BASE_URL);
    
    // Wait for dashboard to load completely
    await page.waitForLoadState('networkidle');
    
    // Navigate to locate the Statistics and Reports section
    // Since no specific locators are provided, we'll use text-based navigation
    const statisticsSection = page.getByText('Statistics and Reports').first();
    await expect(statisticsSection, 'Statistics and Reports section should be visible on dashboard').toBeVisible();
    
    // Verify the section title displays correctly
    await expect(page.getByRole('heading', { name: /Statistics and Reports/i }), 'Statistics and Reports section title should be displayed correctly').toBeVisible();
    
    // Confirm the section content and reports are accessible
    // Look for common report elements or content indicators
    const reportContent = page.locator('[class*="report"], [class*="statistic"], [class*="chart"]').first();
    await expect(reportContent, 'Report content should be accessible within the Statistics and Reports section').toBeVisible();
    
    // Verify the page URL contains dashboard path
    await expect(page, 'Page should remain on dashboard after section verification').toHaveURL(/.*dashboard.*/);
  });
});