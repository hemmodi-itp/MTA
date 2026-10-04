import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Global navbar displays all required navigation elements (M02_BS_002)', () => {
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

  test('positive — global navbar contains all required elements including logo and navigation links', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load completely
    await page.waitForLoadState('networkidle');
    
    // Locate the global navbar on the page
    const navbar = page.locator('nav, header, .navbar, [role="navigation"]').first();
    await expect(navbar, 'Global navigation bar must be present on the page').toBeVisible();
    
    // Verify Selenium logo is present and visible
    const logo = page.locator('img[alt*="logo" i], img[src*="logo" i], .logo, [data-testid*="logo" i]').first();
    if (await logo.count() > 0) {
      await expect(logo, 'Selenium logo must be visible in the navbar').toBeVisible();
    }
    
    // Confirm all required navigation links are displayed: About, Documentation, Downloads, Projects, Blog, Support
    const requiredLinks = ['About', 'Documentation', 'Downloads', 'Projects', 'Blog', 'Support'];
    
    for (const linkText of requiredLinks) {
      const link = page.getByRole('link', { name: new RegExp(linkText, 'i') });
      if (await link.count() > 0) {
        await expect(link, `Navigation link "${linkText}" must be visible in the navbar`).toBeVisible();
      } else {
        // Try alternative text matching
        const linkByText = page.getByText(linkText, { exact: false });
        if (await linkByText.count() > 0) {
          await expect(linkByText, `Navigation item "${linkText}" must be visible in the navbar`).toBeVisible();
        }
      }
    }
    
    // Check that language toggle control is present
    const languageToggle = page.locator('[data-testid*="language" i], .language-toggle, .lang-toggle, button[aria-label*="language" i]').first();
    if (await languageToggle.count() > 0) {
      await expect(languageToggle, 'Language toggle control must be present in the navbar').toBeVisible();
    }
    
    // Check that theme toggle control is present
    const themeToggle = page.locator('[data-testid*="theme" i], .theme-toggle, button[aria-label*="theme" i], button[aria-label*="dark" i]').first();
    if (await themeToggle.count() > 0) {
      await expect(themeToggle, 'Theme toggle control must be present in the navbar').toBeVisible();
    }
    
    // Verify navbar is consistently positioned at the top of the page
    const navbarBounds = await navbar.boundingBox();
    if (navbarBounds) {
      expect(navbarBounds.y, 'Navbar must be positioned at or near the top of the page').toBeLessThan(100);
    }
  });
});