import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Verify page responsive design and technical requirements (M03_BS_013)', () => {
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

  test('positive — dashboard renders correctly on all viewport sizes with proper title and no console errors', async () => {
    // Set up console error monitoring
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Test desktop viewport (1920x1080)
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(BASE_URL);
    
    // Check page title contains AppEvolve and Projects text
    await expect(page, 'Page title should contain AppEvolve and Projects text').toHaveTitle(/AppEvolve.*Projects|Projects.*AppEvolve/);

    // Check for horizontal overflow on desktop
    const desktopBodyWidth = await page.locator('body').evaluate(el => el.scrollWidth);
    const desktopViewportWidth = await page.evaluate(() => window.innerWidth);
    expect(desktopBodyWidth <= desktopViewportWidth, 'Desktop page should not have horizontal overflow').toBeTruthy();

    // Test tablet viewport (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.reload();

    // Check for horizontal overflow on tablet
    const tabletBodyWidth = await page.locator('body').evaluate(el => el.scrollWidth);
    const tabletViewportWidth = await page.evaluate(() => window.innerWidth);
    expect(tabletBodyWidth <= tabletViewportWidth, 'Tablet page should not have horizontal overflow').toBeTruthy();

    // Test mobile viewport (375x667)
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();

    // Check for horizontal overflow on mobile
    const mobileBodyWidth = await page.locator('body').evaluate(el => el.scrollWidth);
    const mobileViewportWidth = await page.evaluate(() => window.innerWidth);
    expect(mobileBodyWidth <= mobileViewportWidth, 'Mobile page should not have horizontal overflow').toBeTruthy();

    // Verify no console errors occurred during page loads
    expect(consoleErrors.length, 'No console errors should occur during page load').toBe(0);
  });
});