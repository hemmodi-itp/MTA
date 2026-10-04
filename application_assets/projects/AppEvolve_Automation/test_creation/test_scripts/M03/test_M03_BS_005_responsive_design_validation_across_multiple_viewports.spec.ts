import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Responsive design validation across multiple viewports (M03_BS_005)', () => {
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

  test('positive — dashboard renders correctly without horizontal overflow across mobile, tablet, and desktop viewports', async () => {
    // Test mobile viewport (375x812)
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Check for horizontal overflow on mobile
    const mobileBodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const mobileViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(mobileBodyScrollWidth <= mobileViewportWidth, 'Mobile viewport should not have horizontal overflow').toBeTruthy();

    // Test tablet viewport (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Check for horizontal overflow on tablet
    const tabletBodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const tabletViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(tabletBodyScrollWidth <= tabletViewportWidth, 'Tablet viewport should not have horizontal overflow').toBeTruthy();

    // Test desktop viewport (1280x800)
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Check for horizontal overflow on desktop
    const desktopBodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const desktopViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(desktopBodyScrollWidth <= desktopViewportWidth, 'Desktop viewport should not have horizontal overflow').toBeTruthy();

    // Verify page renders properly at each viewport by checking basic page structure
    await expect(page.locator('body'), 'Page body should be visible at desktop viewport').toBeVisible();
    await expect(page, 'Dashboard URL should be maintained after viewport changes').toHaveURL(new RegExp(BASE_URL));
  });
});