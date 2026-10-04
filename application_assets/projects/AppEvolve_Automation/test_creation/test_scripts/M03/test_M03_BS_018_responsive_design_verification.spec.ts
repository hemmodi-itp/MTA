import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Responsive Design Verification (M03_BS_018)', () => {
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

  test('positive — dashboard renders properly without horizontal overflow at mobile, tablet, and desktop viewports', async () => {
    // Test mobile viewport (375x812)
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(BASE_URL);
    
    // Verify no horizontal overflow on mobile
    const mobileScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const mobileClientWidth = await page.evaluate(() => document.body.clientWidth);
    await expect(mobileScrollWidth <= 375, 'Mobile viewport should not have horizontal overflow').toBe(true);
    
    // Test tablet viewport (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500); // Allow layout to settle
    
    // Verify no horizontal overflow on tablet
    const tabletScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const tabletClientWidth = await page.evaluate(() => document.body.clientWidth);
    await expect(tabletScrollWidth <= 768, 'Tablet viewport should not have horizontal overflow').toBe(true);
    
    // Test desktop viewport (1280x800)
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.waitForTimeout(500); // Allow layout to settle
    
    // Verify no horizontal overflow on desktop
    const desktopScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const desktopClientWidth = await page.evaluate(() => document.body.clientWidth);
    await expect(desktopScrollWidth <= 1280, 'Desktop viewport should not have horizontal overflow').toBe(true);
    
    // Verify page is still accessible and loaded properly at desktop size
    await expect(page, 'Dashboard should remain accessible after viewport changes').toHaveURL(BASE_URL);
  });
});