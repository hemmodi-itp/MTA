import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe.configure({ mode: 'serial' });

test.describe('Footer contains complete legal and social information (M02_BS_007)', () => {
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

  test('positive — footer displays complete legal and social information', async () => {
    await page.goto(BASE_URL);
    
    // Scroll to the page footer
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Wait for footer to be visible after scrolling
    await page.waitForTimeout(1000);
    
    // Verify copyright information is displayed
    const copyrightText = page.locator('text=/Copyright|©/i').first();
    await expect(copyrightText, 'Copyright information should be visible in footer').toBeVisible();
    
    // Check that GitHub social link is present
    const githubLink = page.locator('a[href*="github.com"]').first();
    await expect(githubLink, 'GitHub social link should be present in footer').toBeVisible();
    
    // Check that Twitter/X social link is present
    const twitterLink = page.locator('a[href*="twitter.com"], a[href*="x.com"]').first();
    await expect(twitterLink, 'Twitter/X social link should be present in footer').toBeVisible();
    
    // Check that LinkedIn social link is present
    const linkedinLink = page.locator('a[href*="linkedin.com"]').first();
    await expect(linkedinLink, 'LinkedIn social link should be present in footer').toBeVisible();
    
    // Check that Slack social link is present
    const slackLink = page.locator('a[href*="slack.com"]').first();
    await expect(slackLink, 'Slack social link should be present in footer').toBeVisible();
    
    // Confirm Apache License notice is displayed
    const licenseText = page.locator('text=/Apache License|Apache|License/i').first();
    await expect(licenseText, 'Apache License notice should be displayed in footer').toBeVisible();
  });
});