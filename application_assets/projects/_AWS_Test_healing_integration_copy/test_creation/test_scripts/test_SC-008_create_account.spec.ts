import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Create Account (SC-008)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — create AWS account button navigates to account creation page', async () => {
    await page.goto(BASE_URL);
    
    const createAccountButton = page.getByRole('button', { name: 'Create an AWS account' });
    await expect(createAccountButton, 'Create AWS account button must be visible on the page').toBeVisible();
    
    await createAccountButton.click();
    
    await expect(page, 'Should navigate to account creation page after clicking create account button').toHaveURL(/\/create-account/);
  });

  test('negative — account creation page navigation failure handling', async () => {
    await page.goto(BASE_URL);
    
    // Simulate network failure or page not found scenario
    await page.route('**/create-account*', route => {
      route.fulfill({
        status: 404,
        contentType: 'text/html',
        body: '<html><body>Page Not Found</body></html>'
      });
    });
    
    const createAccountButton = page.getByRole('button', { name: 'Create an AWS account' });
    await expect(createAccountButton, 'Create AWS account button must be visible before attempting navigation').toBeVisible();
    
    await createAccountButton.click();
    
    await expect(page, 'Should show error page when account creation page fails to load').toHaveURL(/\/404/);
  });
});