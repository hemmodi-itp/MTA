import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Navigate to new project via project links (M03_BS_012)', () => {
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

  test('positive — clicking project link navigates to project details page', async () => {
    await page.goto(BASE_URL);
    
    // User scrolls to view project listings and identifies a project link
    await expect(page.getByRole('button', { name: 'proj-190' }), 'Project link proj-190 should be visible in the project listings').toBeVisible();
    
    // User clicks on the project link
    await page.getByRole('button', { name: 'proj-190' }).click();
    
    // Verify navigation occurred by checking URL pattern
    await expect(page, 'User should be navigated to the selected project detail page').toHaveURL(/proj-190|project.*190/);
  });
});