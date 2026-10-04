import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Page Title Validation (M03_BS_019)', () => {
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

  test('positive — page title contains both AppEvolve and Projects for proper identification', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to fully load
    await page.waitForLoadState('networkidle');
    
    // Get the page title
    const pageTitle = await page.title();
    
    // Verify title contains 'AppEvolve'
    await expect(pageTitle, 'Page title must contain "AppEvolve" for proper branding identification').toContain('AppEvolve');
    
    // Verify title contains 'Projects'
    await expect(pageTitle, 'Page title must contain "Projects" for proper page identification').toContain('Projects');
    
    // Confirm both terms are present in a single assertion for complete validation
    const containsBothTerms = pageTitle.includes('AppEvolve') && pageTitle.includes('Projects');
    await expect(containsBothTerms, 'Page title must contain both "AppEvolve" and "Projects" for complete identification').toBe(true);
  });
});