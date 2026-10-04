import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Grid project card displays complete information and actions (M02_BS_006)', () => {
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

  test('positive — Grid project card contains all required elements with proper functionality', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to Selenium Projects page
    await page.waitForLoadState('networkidle');
    
    // Locate the Grid project card
    const gridCard = page.locator('[data-testid="grid-project-card"]').first();
    await expect(gridCard, 'Grid project card must be visible on the projects page').toBeVisible();
    
    // Verify Grid logo is displayed
    const gridLogo = gridCard.locator('img[alt*="Grid"], img[src*="grid"]').first();
    await expect(gridLogo, 'Grid logo must be displayed in the project card').toBeVisible();
    
    // Confirm project description text is present
    const descriptionText = gridCard.locator('p, div').filter({ hasText: /grid|selenium|browser/i }).first();
    await expect(descriptionText, 'Grid project description text must be present').toBeVisible();
    
    // Check that Download button is visible and actionable
    const downloadButton = gridCard.getByRole('button', { name: /download/i });
    await expect(downloadButton, 'Download button must be visible in Grid project card').toBeVisible();
    await expect(downloadButton, 'Download button must be enabled and actionable').toBeEnabled();
    
    // Verify 'Read more' link is present
    const readMoreLink = gridCard.getByRole('link', { name: /read more|learn more/i });
    await expect(readMoreLink, 'Read more link must be present in Grid project card').toBeVisible();
    
    // Verify the read more link has a valid href attribute
    const readMoreHref = await readMoreLink.getAttribute('href');
    await expect(readMoreHref, 'Read more link must have a valid href attribute').toBeTruthy();
  });
});