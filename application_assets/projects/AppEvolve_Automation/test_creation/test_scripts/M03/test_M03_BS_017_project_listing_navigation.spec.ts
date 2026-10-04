import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Project Listing Navigation (M03_BS_017)', () => {
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

  test('positive — user scrolls to project listing and navigates to individual project successfully', async () => {
    await page.goto(BASE_URL);
    
    // User scrolls down on the dashboard page to reveal project listings
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000); // Allow scroll animation to complete
    
    // User verifies project listing section is visible by checking for project links
    await expect(page.getByRole('button', { name: 'proj-190' }), 'First project link should be visible in the listing').toBeVisible();
    await expect(page.getByRole('button', { name: 'proj-201' }), 'Second project link should be visible in the listing').toBeVisible();
    await expect(page.getByRole('button', { name: 'proj-194' }), 'Third project link should be visible in the listing').toBeVisible();
    await expect(page.getByRole('button', { name: 'proj-2' }), 'Fourth project link should be visible in the listing').toBeVisible();
    
    // User clicks on a project link from the listing
    await page.getByRole('button', { name: 'proj-190' }).click();
    
    // User verifies navigation to the selected project works
    await expect(page, 'URL should change to indicate navigation to project occurred').toHaveURL(/proj/);
  });
});