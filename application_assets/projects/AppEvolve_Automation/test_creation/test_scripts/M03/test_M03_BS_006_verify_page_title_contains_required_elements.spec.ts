import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Verify page title contains required elements (M03_BS_006)', () => {
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

  test('positive — page title contains both AppEvolve and Projects text', async () => {
    await page.goto(BASE_URL);
    
    const pageTitle = await page.title();
    
    await expect(page, 'Page title must contain AppEvolve text for proper brand identification').toHaveTitle(/AppEvolve/);
    await expect(page, 'Page title must contain Projects text to indicate current page context').toHaveTitle(/Projects/);
    
    expect(pageTitle, 'Full page title must contain both required elements for SEO compliance').toContain('AppEvolve');
    expect(pageTitle, 'Full page title must contain both required elements for proper page identification').toContain('Projects');
  });
});