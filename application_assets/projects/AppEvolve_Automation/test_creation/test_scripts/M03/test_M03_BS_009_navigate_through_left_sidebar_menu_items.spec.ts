import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Navigate through left sidebar menu items (M03_BS_009)', () => {
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

  test('positive — navigate through all left sidebar menu items successfully', async () => {
    await page.goto(BASE_URL);
    
    // User clicks on Settings in the left navigation bar
    const settingsButton = page.locator('div>div>div>div>span>button');
    await expect(settingsButton, 'Settings menu item button should be visible and clickable').toBeVisible();
    await settingsButton.click();
    
    // User clicks on Help from the left navigation bar
    const helpButton = page.locator('div>div>div>div>button');
    await expect(helpButton, 'Help menu item button should be visible and clickable').toBeVisible();
    await helpButton.click();
    
    // User clicks on Dashboard in the left navigation bar
    const dashboardButton = page.locator('div>div>div>div:nth-of-type(4)>div>div>div:nth-of-type(2)>button');
    await expect(dashboardButton, 'Dashboard menu item button should be visible and clickable').toBeVisible();
    await dashboardButton.click();
    
    // User clicks on Projects in the left navigation bar
    const projectsButton = page.locator('div>div>div:nth-of-type(2)>header>div>div>button');
    await expect(projectsButton, 'Projects menu item button should be visible and clickable').toBeVisible();
    await projectsButton.click();
  });
});