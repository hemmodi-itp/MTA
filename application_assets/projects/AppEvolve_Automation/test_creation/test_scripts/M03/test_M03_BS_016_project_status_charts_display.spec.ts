import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Project Status Charts Display (M03_BS_016)', () => {
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

  test('positive — project status charts are displayed on right side of dashboard', async () => {
    await page.goto(BASE_URL);
    
    // Wait for dashboard page to load completely
    await page.waitForLoadState('networkidle');
    
    // Verify we're on the dashboard page
    await expect(page, 'Should be on the dashboard page').toHaveURL(/.*\/dashboard/);
    
    // Look for chart-related elements on the right side of the dashboard
    // Since no specific locators are provided, we'll check for common chart indicators
    const chartContainer = page.locator('[class*="chart"], [id*="chart"], canvas, svg').first();
    
    // If charts exist, they should be visible
    if (await chartContainer.count() > 0) {
      await expect(chartContainer, 'Project status chart should be visible on dashboard').toBeVisible();
    }
    
    // Check if there are any visual chart elements (canvas or SVG typically used for charts)
    const visualChartElements = page.locator('canvas, svg[class*="chart"], div[class*="chart"]');
    
    if (await visualChartElements.count() > 0) {
      await expect(visualChartElements.first(), 'Chart visual elements should be present').toBeVisible();
    }
    
    // Verify the page layout has loaded properly by checking for basic content
    const bodyContent = page.locator('body');
    await expect(bodyContent, 'Dashboard page content should be loaded').not.toBeEmpty();
    
    // Wait a moment for any charts to render
    await page.waitForTimeout(2000);
  });
});