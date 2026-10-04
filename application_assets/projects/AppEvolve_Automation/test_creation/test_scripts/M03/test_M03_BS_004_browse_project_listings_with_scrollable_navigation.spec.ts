import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Browse project listings with scrollable navigation (M03_BS_004)', () => {
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

  test('positive — scroll to view project listings and click navigation links successfully', async () => {
    await page.goto(BASE_URL);
    
    // Wait for the page to load completely
    await page.waitForLoadState('networkidle');
    
    // Scroll down to view project listings
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight / 2);
    });
    
    // Wait a moment for any dynamic content to load after scrolling
    await page.waitForTimeout(1000);
    
    // Verify project listings are visible after scrolling
    await expect(page.getByRole('button', { name: 'proj-190' }), 'Project 190 button should be visible in listings').toBeVisible();
    await expect(page.getByRole('button', { name: 'proj-201' }), 'Project 201 button should be visible in listings').toBeVisible();
    await expect(page.getByRole('button', { name: 'proj-194' }), 'Project 194 button should be visible in listings').toBeVisible();
    
    // Verify navigation links are clickable by clicking on the first project
    await page.getByRole('button', { name: 'proj-190' }).click();
    
    // Wait for any navigation or page changes
    await page.waitForTimeout(1000);
    
    // Navigate back to test another project link
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Scroll down again to access project listings
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight / 2);
    });
    
    await page.waitForTimeout(1000);
    
    // Click on another project to verify navigation functionality
    await page.getByRole('button', { name: 'proj-201' }).click();
    
    // Wait for any navigation or page changes
    await page.waitForTimeout(1000);
    
    // Test the third project link
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight / 2);
    });
    
    await page.waitForTimeout(1000);
    
    // Verify the third project link is also functional
    await page.getByRole('button', { name: 'proj-194' }).click();
  });
});