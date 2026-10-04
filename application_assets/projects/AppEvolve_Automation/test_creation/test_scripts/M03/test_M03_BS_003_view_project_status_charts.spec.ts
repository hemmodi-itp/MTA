import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('View project status charts (M03_BS_003)', () => {
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

  test('positive — view and interact with all project status charts on right side of dashboard', async () => {
    await page.goto(BASE_URL);

    // User views the right side of the dashboard page and observes project status charts
    await expect(page.getByRole('button', { name: 'Users\n\n3\n\nTotal' }), 'Users chart element should be visible on right side of dashboard').toBeVisible();
    await expect(page.getByRole('button', { name: 'Clients\n\n2\n\nTotal' }), 'Clients chart element should be visible on right side of dashboard').toBeVisible();
    await expect(page.getByRole('button', { name: 'Projects\n\n143\n\nTotal' }), 'Projects chart element showing metrics should be visible on dashboard').toBeVisible();
    await expect(page.getByRole('button', { name: 'Profiles\n\n0\n\nTotal' }), 'Profiles chart element should be visible on right side of dashboard').toBeVisible();

    // User interacts with chart elements if applicable
    await page.getByRole('button', { name: 'Users\n\n3\n\nTotal' }).click();
    await expect(page.getByRole('button', { name: 'Users\n\n3\n\nTotal' }), 'Users chart should remain accessible after interaction').toBeVisible();

    await page.getByRole('button', { name: 'Clients\n\n2\n\nTotal' }).click();
    await expect(page.getByRole('button', { name: 'Clients\n\n2\n\nTotal' }), 'Clients chart should remain accessible after interaction').toBeVisible();

    await page.getByRole('button', { name: 'Projects\n\n143\n\nTotal' }).click();
    await expect(page.getByRole('button', { name: 'Projects\n\n143\n\nTotal' }), 'Projects chart should remain accessible after interaction').toBeVisible();

    await page.getByRole('button', { name: 'Profiles\n\n0\n\nTotal' }).click();
    await expect(page.getByRole('button', { name: 'Profiles\n\n0\n\nTotal' }), 'Profiles chart should remain accessible after interaction').toBeVisible();
  });
});