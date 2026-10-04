import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('WebDriver project card displays complete information and actions (M02_BS_004)', () => {
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

  test('positive — WebDriver project card contains all required elements and allows interaction', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to Selenium Projects page first
    await page.waitForLoadState('networkidle');
    
    // Since no specific locators are provided, we'll use generic approaches to locate the WebDriver project card
    // Look for WebDriver project card by searching for text content that would indicate it's the WebDriver section
    const webDriverSection = page.locator('text=WebDriver').first();
    await expect(webDriverSection, 'WebDriver project card should be visible on the page').toBeVisible();
    
    // Find the parent container that holds all WebDriver project information
    const projectCard = webDriverSection.locator('..').locator('..');
    
    // Verify WebDriver logo is displayed - look for img elements within the project card area
    const logoImage = projectCard.locator('img').first();
    await expect(logoImage, 'WebDriver logo image should be displayed in the project card').toBeVisible();
    
    // Confirm project description text is present - look for descriptive text content
    const descriptionText = projectCard.locator('text=/browser automation|selenium|webdriver/i').first();
    await expect(descriptionText, 'Project description text should be present in the WebDriver card').toBeVisible();
    
    // Check that Download button is visible and actionable
    const downloadButton = projectCard.getByRole('button', { name: /download/i });
    await expect(downloadButton, 'Download button should be visible in the WebDriver project card').toBeVisible();
    await expect(downloadButton, 'Download button should be enabled and actionable').toBeEnabled();
    
    // Verify 'Read more' link is present
    const readMoreLink = projectCard.getByRole('link', { name: /read more|learn more|more info/i });
    await expect(readMoreLink, 'Read more link should be present in the WebDriver project card').toBeVisible();
    
    // Test that the Download button is actually clickable (without completing the download)
    await downloadButton.hover();
    await expect(downloadButton, 'Download button should remain enabled when hovered').toBeEnabled();
    
    // Test that the Read more link is actionable
    await readMoreLink.hover();
    const readMoreHref = await readMoreLink.getAttribute('href');
    expect(readMoreHref, 'Read more link should have a valid href attribute').toBeTruthy();
  });
});