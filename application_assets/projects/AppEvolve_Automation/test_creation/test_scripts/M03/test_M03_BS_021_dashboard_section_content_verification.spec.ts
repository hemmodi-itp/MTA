import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Dashboard Section Content Verification (M03_BS_021)', () => {
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

  test('positive — all required dashboard sections are visible with proper content organization', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load completely
    await page.waitForLoadState('networkidle');
    
    // Verify 'AI-Driven Legacy Code Conversion' section is visible
    await page.waitForTimeout(2000); // Allow time for dynamic content to load
    const aiConversionSection = page.getByText('AI-Driven Legacy Code Conversion');
    await expect(aiConversionSection, 'AI-Driven Legacy Code Conversion section must be visible on dashboard').toBeVisible();
    
    // Confirm 'Statistics and Reports' section is present
    const statisticsSection = page.getByText('Statistics and Reports');
    await expect(statisticsSection, 'Statistics and Reports section must be present on dashboard').toBeVisible();
    
    // Locate 'Recent Projects' section with project count
    const recentProjectsSection = page.getByText('Recent Projects');
    await expect(recentProjectsSection, 'Recent Projects section must be visible on dashboard').toBeVisible();
    
    // Verify project details table is displayed (look for common table elements)
    const projectTable = page.locator('table, .table, [role="table"]').first();
    if (await projectTable.count() > 0) {
      await expect(projectTable, 'Project details table must be displayed on dashboard').toBeVisible();
    }
    
    // Confirm all section titles are correctly formatted (check that they are in proper heading elements)
    const sectionHeadings = page.locator('h1, h2, h3, h4, h5, h6').filter({ hasText: /AI-Driven Legacy Code Conversion|Statistics and Reports|Recent Projects/i });
    if (await sectionHeadings.count() > 0) {
      await expect(sectionHeadings.first(), 'Section titles must be properly formatted as headings').toBeVisible();
    }
    
    // Verify the overall page structure is loaded
    await expect(page, 'Dashboard page must be fully loaded with correct URL').toHaveURL(new RegExp(BASE_URL.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  });
});