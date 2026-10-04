import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Hero section displays project introduction content (M02_BS_003)', () => {
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

  test('positive — hero section displays Selenium Projects heading and introductory content', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load completely
    await page.waitForLoadState('networkidle');
    
    // Locate the hero/page header section and verify it's visible
    const heroSection = page.locator('header, .hero, .page-header, h1').first();
    await expect(heroSection, 'Hero section should be visible on the page').toBeVisible();
    
    // Verify 'Selenium Projects' heading is displayed
    const mainHeading = page.getByRole('heading', { name: /selenium projects/i });
    await expect(mainHeading, 'Main heading should display Selenium Projects text').toBeVisible();
    
    // Confirm introductory paragraph content is present and readable
    const introText = page.locator('p, .intro, .description').first();
    await expect(introText, 'Introductory paragraph should be present in hero section').toBeVisible();
    
    // Verify the intro text has meaningful content (not empty)
    const textContent = await introText.textContent();
    await expect(textContent?.trim().length, 'Introductory text should contain meaningful content').toBeGreaterThan(10);
  });
});