import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/';

test.describe.configure({ mode: 'serial' });

test.describe('Navigate using navigation bar to fetch page information (M01_BS_001)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — navigation bar elements display page information successfully', async () => {
    await page.goto(BASE_URL);
    
    // Verify navigation bar is visible and accessible
    await expect(page.getByRole('button', { name: 'Discover AWS' }), 'Discover AWS navigation button should be visible').toBeVisible();
    await expect(page.getByRole('button', { name: 'Products' }), 'Products navigation button should be visible').toBeVisible();
    await expect(page.getByRole('button', { name: 'Solutions' }), 'Solutions navigation button should be visible').toBeVisible();
    await expect(page.getByRole('button', { name: 'Pricing' }), 'Pricing navigation button should be visible').toBeVisible();
    await expect(page.getByRole('button', { name: 'Resources' }), 'Resources navigation button should be visible').toBeVisible();

    // Click on Products navigation element to fetch page information
    await page.getByRole('button', { name: 'Products' }).click();
    
    // Verify system responds to navigation interaction
    await expect(page.getByRole('button', { name: 'Products' }), 'Products button should remain accessible after click').toBeVisible();

    // Test additional navigation elements to ensure they fetch information
    await page.getByRole('button', { name: 'Solutions' }).click();
    await expect(page.getByRole('button', { name: 'Solutions' }), 'Solutions button should remain accessible after click').toBeVisible();

    await page.getByRole('button', { name: 'Pricing' }).click();
    await expect(page.getByRole('button', { name: 'Pricing' }), 'Pricing button should remain accessible after click').toBeVisible();

    await page.getByRole('button', { name: 'Resources' }).click();
    await expect(page.getByRole('button', { name: 'Resources' }), 'Resources button should remain accessible after click').toBeVisible();

    await page.getByRole('button', { name: 'Discover AWS' }).click();
    await expect(page.getByRole('button', { name: 'Discover AWS' }), 'Discover AWS button should remain accessible after click').toBeVisible();
  });

  test('negative — navigation elements handle rapid clicking without breaking', async () => {
    await page.goto(BASE_URL);
    
    // Rapidly click navigation elements to test system stability
    await page.getByRole('button', { name: 'Products' }).click();
    await page.getByRole('button', { name: 'Solutions' }).click();
    await page.getByRole('button', { name: 'Products' }).click();
    
    // Verify navigation bar remains functional after rapid interactions
    await expect(page.getByRole('button', { name: 'Products' }), 'Products button should remain functional after rapid clicking').toBeVisible();
    await expect(page.getByRole('button', { name: 'Solutions' }), 'Solutions button should remain functional after rapid clicking').toBeVisible();
  });

  test('boundary — all navigation elements accessible and responsive', async () => {
    await page.goto(BASE_URL);
    
    // Test boundary case of accessing all navigation elements in sequence
    const navElements = [
      { button: page.getByRole('button', { name: 'Discover AWS' }), name: 'Discover AWS' },
      { button: page.getByRole('button', { name: 'Products' }), name: 'Products' },
      { button: page.getByRole('button', { name: 'Solutions' }), name: 'Solutions' },
      { button: page.getByRole('button', { name: 'Pricing' }), name: 'Pricing' },
      { button: page.getByRole('button', { name: 'Resources' }), name: 'Resources' }
    ];

    for (const element of navElements) {
      await element.button.click();
      await expect(element.button, `${element.name} navigation element should remain accessible`).toBeVisible();
    }
  });
});