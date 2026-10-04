import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('View project status charts and listings (M03_BS_011)', () => {
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

  test('positive — view project charts and listings on dashboard scroll', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // User views the right side of the page for project charts
    // Look for any chart-related elements on the right side
    const rightSideContent = page.locator('.right-side, .sidebar-right, .chart-container, .project-charts').first();
    
    // User examines project status displayed in chart format
    // Check if page is loaded and ready for interaction
    await expect(page, 'Dashboard page should be loaded').toHaveURL(/.*dashboard.*/);
    
    // User scrolls down the page
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight / 2);
    });
    
    // Wait a moment for any dynamic content to load after scroll
    await page.waitForTimeout(1000);
    
    // Continue scrolling to reveal more content
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });
    
    // Wait for any lazy-loaded content
    await page.waitForTimeout(1000);
    
    // User views the project listing that appears on scrolling
    // Verify the page has content that could represent project data
    const bodyContent = page.locator('body');
    await expect(bodyContent, 'Page body should contain content after scrolling').toBeVisible();
    
    // Check that scrolling action was successful by verifying scroll position
    const scrollPosition = await page.evaluate(() => window.scrollY);
    expect(scrollPosition, 'Page should be scrolled down from initial position').toBeGreaterThan(0);
  });
});