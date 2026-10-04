import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Page layout adapts correctly across different viewport sizes (M02_BS_008)', () => {
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

  test('positive — page layout adapts correctly across mobile, tablet, and desktop viewports', async () => {
    // Load the Selenium Projects page
    await page.goto(BASE_URL);

    // Test mobile viewport (375px width)
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForLoadState('networkidle');

    // Verify no horizontal overflow on mobile
    const mobileBodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const mobileViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(mobileBodyScrollWidth <= mobileViewportWidth, 'Mobile layout should not have horizontal overflow').toBeTruthy();

    // Test tablet viewport (768px width)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForLoadState('networkidle');

    // Verify no horizontal overflow on tablet
    const tabletBodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const tabletViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(tabletBodyScrollWidth <= tabletViewportWidth, 'Tablet layout should not have horizontal overflow').toBeTruthy();

    // Test desktop viewport (1280px width)
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForLoadState('networkidle');

    // Verify no horizontal overflow on desktop
    const desktopBodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const desktopViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(desktopBodyScrollWidth <= desktopViewportWidth, 'Desktop layout should not have horizontal overflow').toBeTruthy();

    // Verify page remains accessible across all viewport sizes
    await expect(page, 'Page should remain accessible on desktop viewport').toHaveURL(BASE_URL);

    // Test responsiveness by checking viewport changes don't break the page
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(100);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForTimeout(100);

    // Verify page is still functional after viewport changes
    await expect(page, 'Page should remain functional after viewport changes').not.toHaveURL(/error/);
  });
});