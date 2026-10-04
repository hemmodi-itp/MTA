import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/';

test.describe.configure({ mode: 'serial' });

test.describe('View client images through image carousel (M01_BS_003)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — navigate through client images using carousel controls', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load and carousel to be present
    await page.waitForLoadState('domcontentloaded');
    
    // Verify carousel navigation buttons are visible
    const firstNavButton = page.locator('div>section>div>div>div:nth-of-type(2)>div>div:nth-of-type(2)>div>button');
    const secondNavButton = page.locator('div>section>div>div>div:nth-of-type(2)>div>div:nth-of-type(2)>div>button:nth-of-type(2)');
    
    await expect(firstNavButton, 'First carousel navigation button must be visible').toBeVisible();
    await expect(secondNavButton, 'Second carousel navigation button must be visible').toBeVisible();
    
    // Click first navigation button to navigate through carousel
    await firstNavButton.click();
    
    // Wait for carousel transition
    await page.waitForTimeout(1000);
    
    // Click second navigation button to continue navigating
    await secondNavButton.click();
    
    // Wait for carousel transition
    await page.waitForTimeout(1000);
    
    // Verify navigation buttons are still functional after interaction
    await expect(firstNavButton, 'First navigation button must remain clickable after use').toBeEnabled();
    await expect(secondNavButton, 'Second navigation button must remain clickable after use').toBeEnabled();
  });

  test('negative — carousel navigation with rapid successive clicks', async () => {
    await page.goto(BASE_URL);
    
    await page.waitForLoadState('domcontentloaded');
    
    const firstNavButton = page.locator('div>section>div>div>div:nth-of-type(2)>div>div:nth-of-type(2)>div>button');
    const secondNavButton = page.locator('div>section>div>div>div:nth-of-type(2)>div>div:nth-of-type(2)>div>button:nth-of-type(2)');
    
    // Rapidly click navigation buttons to test carousel stability
    for (let i = 0; i < 5; i++) {
      await firstNavButton.click();
      await secondNavButton.click();
    }
    
    // Verify carousel remains functional after rapid clicking
    await expect(firstNavButton, 'Carousel navigation must remain stable after rapid clicking').toBeVisible();
    await expect(secondNavButton, 'Carousel navigation must remain stable after rapid clicking').toBeVisible();
  });

  test('boundary — carousel navigation at page load boundary', async () => {
    await page.goto(BASE_URL);
    
    // Attempt to interact with carousel immediately after navigation
    const firstNavButton = page.locator('div>section>div>div>div:nth-of-type(2)>div>div:nth-of-type(2)>div>button');
    
    // Click navigation button before full page load to test boundary condition
    await firstNavButton.click();
    
    await page.waitForLoadState('domcontentloaded');
    
    // Verify carousel functionality is maintained even with early interaction
    await expect(firstNavButton, 'Carousel must handle early interaction gracefully').toBeVisible();
    
    // Verify second button becomes available
    const secondNavButton = page.locator('div>section>div>div>div:nth-of-type(2)>div>div:nth-of-type(2)>div>button:nth-of-type(2)');
    await expect(secondNavButton, 'Second navigation button must be available after page load').toBeVisible();
  });
});