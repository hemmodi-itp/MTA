import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Verify dashboard sections visibility and content (M03_BS_008)', () => {
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

  test('positive — all dashboard sections are visible with correct content structure', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Verify 'AI-Driven Legacy Code Conversion' section is visible
    await expect(page.getByText('AI-Driven Legacy Code Conversion'), 'AI-Driven Legacy Code Conversion section must be visible on dashboard').toBeVisible();
    
    // Verify 'Statistics and Reports' section is visible
    await expect(page.getByText('Statistics and Reports'), 'Statistics and Reports section must be visible on dashboard').toBeVisible();
    
    // Verify 'Recent Projects (194)' section is visible
    await expect(page.getByText(/Recent Projects.*194/), 'Recent Projects section with count must be visible on dashboard').toBeVisible();
    
    // Confirm project details table is present - look for common table elements
    const tableExists = await page.locator('table').count() > 0 || 
                       await page.locator('[role="table"]').count() > 0 ||
                       await page.locator('.table').count() > 0;
    
    expect(tableExists, 'Project details table must be present on dashboard').toBeTruthy();
    
    // Verify URL is correct
    await expect(page, 'User must be on the dashboard page').toHaveURL(/.*dashboard/);
  });
});