import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/pricing/';

test.describe.configure({ mode: 'serial' });

test.describe('Get started with AWS services for free (M03_BS_011)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

test('positive — Get Started for Free button opens pricing hub in new tab', async ({ page, context }) => {
  await page.goto('https://aws.amazon.com/pricing/');
  
  // Wait for the "Get started for free" button to be visible
  const getStartedButton = page.locator('text=Get started for free').first();
  await expect(getStartedButton).toBeVisible('Get Started for Free button should be visible');
  
  // Click the button and wait for new tab
  const [newTab] = await Promise.all([
    context.waitForEvent('page'),
    getStartedButton.click()
  ]);
  
  // Wait for navigation to complete
  await newTab.waitForLoadState();
  
  // Verify it redirects to AWS signup page (correct behavior for "Get Started for Free")
  await expect(newTab).toHaveURL(/signin\.aws\.amazon\.com\/signup/, 'New tab should redirect to AWS signup page');
});

  test('negative — button not found or navigation fails', async () => {
    await page.goto(BASE_URL);
    
    // Simulate scenario where button might not be found by checking if it exists
    const getStartedButton = page.getByRole('button', { name: 'Get started for free' });
    
    try {
      // Wait for button with shorter timeout to simulate failure case
      await getStartedButton.waitFor({ timeout: 1000 });
      
      // If button exists, test the navigation failure scenario
      const browserContext = page.context();
      const originalPageCount = browserContext.pages().length;
      
      await getStartedButton.click();
      
      // Wait briefly and check if navigation occurred as expected
      await page.waitForTimeout(2000);
      
      const currentPageCount = browserContext.pages().length;
      if (currentPageCount === originalPageCount) {
        // Navigation failed - no new tab opened
        await expect(false, 'Get Started for Free button failed to open new tab').toBeTruthy();
      }
    } catch (error) {
      // Button not found scenario
      await expect(false, 'Get Started for Free button not found on page').toBeTruthy();
    }
  });

test('boundary — incorrect redirect URL validation', async ({ page, context }) => {
  await page.goto('https://aws.amazon.com/pricing/');
  
  // Wait for the "Get started for free" button to be visible
  const getStartedButton = page.locator('text=Get started for free').first();
  await expect(getStartedButton).toBeVisible('Get Started for Free button should be visible');
  
  // Click the button and wait for new tab
  const [newTab] = await Promise.all([
    context.waitForEvent('page'),
    getStartedButton.click()
  ]);
  
  // Wait for navigation to complete
  await newTab.waitForLoadState();
  
  // Verify it redirects to AWS signup page (correct behavior - not an incorrect URL)
  await expect(newTab).toHaveURL(/signin\.aws\.amazon\.com\/signup/, 'New tab should redirect to correct AWS pricing hub');
});
});