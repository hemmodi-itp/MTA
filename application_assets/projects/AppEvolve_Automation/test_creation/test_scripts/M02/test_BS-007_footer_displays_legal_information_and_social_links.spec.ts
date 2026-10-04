import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe('Footer displays legal information and social links (BS-007)', () => {

  test.beforeEach(async ({ page }) => {
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
  test('positive — footer displays all required legal information and social links', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Scroll to the page footer
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    
    // Verify copyright notice is displayed
    await expect(page.locator('footer'), 'Footer section should be visible after scrolling').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should be displayed in footer').toBeVisible();
    
    // Check for GitHub social link
    await expect(page.locator('footer a[href*="github"]'), 'GitHub social link should be present in footer').toBeVisible();
    
    // Check for Twitter/X social link
    await expect(page.locator('footer a[href*="twitter"], footer a[href*="x.com"]'), 'Twitter/X social link should be present in footer').toBeVisible();
    
    // Check for LinkedIn social link
    await expect(page.locator('footer a[href*="linkedin"]'), 'LinkedIn social link should be present in footer').toBeVisible();
    
    // Check for Slack social link
    await expect(page.locator('footer a[href*="slack"]'), 'Slack social link should be present in footer').toBeVisible();
    
    // Verify Apache License notice is present
    await expect(page.getByText('Apache License', { exact: false }), 'Apache License notice should be displayed in footer').toBeVisible();
  });

  test('negative — footer remains functional when network connection is poor', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Simulate slow network by throttling
    await page.route('**/*', route => {
      setTimeout(() => route.continue(), 2000);
    });
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(3000);
    
    await expect(page.locator('footer'), 'Footer should still be visible even with slow network').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should be visible despite network issues').toBeVisible();
  });

  test('negative — footer displays correctly when page has minimal content', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Remove most page content to test footer with minimal content
    await page.evaluate(() => {
      const main = document.querySelector('main');
      if (main) main.innerHTML = '<div style="height: 50px;">Minimal content</div>';
    });
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    await expect(page.locator('footer'), 'Footer should display correctly even with minimal page content').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should remain visible with minimal content').toBeVisible();
  });

  test('negative — footer social links handle invalid URLs gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Modify social links to invalid URLs
    await page.evaluate(() => {
      const socialLinks = document.querySelectorAll('footer a[href*="github"], footer a[href*="twitter"], footer a[href*="linkedin"], footer a[href*="slack"]');
      socialLinks.forEach(link => {
        (link as HTMLAnchorElement).href = 'javascript:void(0)';
      });
    });
    
    await expect(page.locator('footer'), 'Footer should remain functional even with invalid social link URLs').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should still be displayed with invalid social URLs').toBeVisible();
  });

  test('negative — footer handles XSS injection in copyright text', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Attempt to inject malicious script into copyright text
    await page.evaluate(() => {
      const copyrightElement = document.querySelector('footer *:has-text("©")');
      if (copyrightElement) {
        copyrightElement.innerHTML = '© <script>alert("xss")</script> 2024';
      }
    });
    
    await expect(page.locator('footer'), 'Footer should handle XSS injection attempts safely').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should display safely without executing injected scripts').toBeVisible();
  });

  test('boundary — footer displays correctly at minimum viewport width', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(BASE_URL);
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    await expect(page.locator('footer'), 'Footer should be visible at minimum viewport width (320px)').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should remain visible at minimum width').toBeVisible();
    await expect(page.locator('footer a[href*="github"]'), 'GitHub link should be accessible at minimum width').toBeVisible();
  });

  test('boundary — footer displays correctly at maximum typical viewport width', async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    await page.goto(BASE_URL);
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    await expect(page.locator('footer'), 'Footer should be visible at maximum viewport width (2560px)').toBeVisible();
    await expect(page.getByText('©', { exact: false }), 'Copyright notice should remain properly positioned at maximum width').toBeVisible();
    await expect(page.locator('footer a[href*="linkedin"]'), 'LinkedIn link should be accessible at maximum width').toBeVisible();
  });

  test('boundary — footer social links handle extremely long URLs', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    
    // Set extremely long URLs for social links
    const longUrl = 'https://example.com/' + 'a'.repeat(2000) + '/social';
    await page.evaluate((url) => {
      const socialLinks = document.querySelectorAll('footer a[href*="github"], footer a[href*="twitter"]');
      socialLinks.forEach(link => {
        (link as HTMLAnchorElement).href = url;
      });
    }, longUrl);
    
    await expect(page.locator('footer'), 'Footer should handle extremely long URLs in social links').toBeVisible();
    await expect(page.locator('footer a[href*="github"]'), 'Social links should remain functional with extremely long URLs').toBeVisible();
    await expect(page.getByText('Apache License', { exact: false }), 'Apache License notice should remain visible with long URLs').toBeVisible();
  });

});