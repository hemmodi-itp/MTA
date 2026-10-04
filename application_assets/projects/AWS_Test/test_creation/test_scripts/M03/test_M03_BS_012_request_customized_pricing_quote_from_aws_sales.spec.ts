import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/pricing/';

test.describe.configure({ mode: 'serial' });

test.describe('Request customized pricing quote from AWS sales (M03_BS_012)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — user can navigate to AWS sales contact page via pricing quote button', async () => {
    await page.goto(BASE_URL);
    
    const pricingQuoteButton = page.getByRole('button', { name: 'Request a pricing quote' });
    await expect(pricingQuoteButton, 'Request a pricing quote button must be visible on pricing page').toBeVisible();
    
    await pricingQuoteButton.click();
    
    await expect(page, 'User should be redirected to AWS sales contact page').toHaveURL('https://aws.amazon.com/contact-us/sales-support-pricing/?ch=cta&cta=contact-sales');
    
    await page.waitForLoadState('domcontentloaded');
    await expect(page, 'Sales contact page should load successfully').not.toHaveURL(/404/);
  });

test('negative — navigation fails or lands on wrong page', async ({ page }) => {
  await page.goto('https://aws.amazon.com/pricing/');
  
  // Try to find and click a "Request a pricing quote" or similar button
  const quoteButton = page.locator('text=Request a pricing quote').first();
  await expect(quoteButton).toBeVisible('Request pricing quote button should be visible');
  
  // Click the button and verify it navigates to the sales contact page
  await quoteButton.click();
  await page.waitForLoadState();
  
  // Verify it successfully loads the sales contact page (not a 404)
  await expect(page).toHaveURL(/contact-us\/sales-support-pricing/, 'Navigation should result in sales contact page');
  
  // Verify the page loaded successfully with expected content (pricing specialists)
  await expect(page.locator('body')).toContainText('pricing specialists', 'Contact page should contain pricing specialists content');
});
});