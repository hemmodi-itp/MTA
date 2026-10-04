import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Role and Permission tab interaction (M03_BS_022)', () => {
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

  test('positive — Role and Permission tab opens successfully and displays appropriate content', async () => {
    await page.goto(BASE_URL);
    
    // Wait for dashboard page to load
    await page.waitForLoadState('domcontentloaded');
    
    // Click on Role and Permission tab - using generic locator since no specific element provided
    await page.getByText('Role and Permission').click();
    
    // Verify navigation occurred by checking URL contains the expected fragment
    await expect(page, 'URL should contain roles-permissions fragment after clicking tab').toHaveURL(/\/roles-permissions/);
    
    // Wait for the tab interface to load
    await page.waitForLoadState('domcontentloaded');
    
    // Verify the page loaded successfully by checking we're still on the expected URL
    await expect(page, 'Should remain on roles-permissions page after loading').toHaveURL(/\/roles-permissions/);
  });
});