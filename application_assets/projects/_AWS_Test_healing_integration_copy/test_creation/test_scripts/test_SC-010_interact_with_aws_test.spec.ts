import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Interact with AWS_Test (SC-010)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — interact with all available AWS page elements successfully', async () => {
    await page.goto(BASE_URL);
    
    // Verify page is loaded
    await expect(page, 'AWS page should be loaded').toHaveURL(/aws\.amazon\.com/);
    
    // Interact with cookie consent buttons if they appear
    const acceptButton = page.getByRole('button', { name: 'Accept' });
    if (await acceptButton.isVisible()) {
      await acceptButton.click();
      await expect(acceptButton, 'Accept button should be clicked').not.toBeVisible();
    }
    
    const customizeButton = page.getByRole('button', { name: 'Customize' });
    if (await customizeButton.isVisible()) {
      await customizeButton.click();
    }
    
    const declineButton = page.getByRole('button', { name: 'Decline' });
    if (await declineButton.isVisible()) {
      await declineButton.click();
    }
    
    const cancelButton = page.getByRole('button', { name: 'Cancel' });
    if (await cancelButton.isVisible()) {
      await cancelButton.click();
    }
    
    // Navigate to AWS Marketplace
    const marketplaceLink = page.getByRole('link', { name: 'AWS Marketplace' });
    if (await marketplaceLink.isVisible()) {
      await marketplaceLink.click();
      await expect(page, 'Should navigate to AWS Marketplace page').toHaveURL(/marketplace/);
    }
    
    // Go back to base URL for account creation test
    await page.goto(BASE_URL);
    
    // Interact with account creation button
    const createAccountButton = page.getByRole('button', { name: 'Create an AWS account' });
    if (await createAccountButton.isVisible()) {
      await expect(createAccountButton, 'Create AWS account button should be visible').toBeVisible();
      await createAccountButton.click();
    }
  });

  test('negative — attempt to interact with nonexistent elements', async () => {
    await page.goto(BASE_URL);
    
    // Verify page loads despite missing elements
    await expect(page, 'Page should still load even when expected elements are missing').toHaveURL(/aws\.amazon\.com/);
    
    // Try to find elements that may not exist
    const acceptButton = page.getByRole('button', { name: 'Accept' });
    const declineButton = page.getByRole('button', { name: 'Decline' });
    const customizeButton = page.getByRole('button', { name: 'Customize' });
    
    // Test that page remains functional even if cookie buttons are not present
    const acceptVisible = await acceptButton.isVisible().catch(() => false);
    const declineVisible = await declineButton.isVisible().catch(() => false);
    const customizeVisible = await customizeButton.isVisible().catch(() => false);
    
    // At least one main navigation element should be present
    const marketplaceLink = page.getByRole('link', { name: 'AWS Marketplace' });
    const createAccountButton = page.getByRole('button', { name: 'Create an AWS account' });
    
    const hasMarketplace = await marketplaceLink.isVisible().catch(() => false);
    const hasCreateAccount = await createAccountButton.isVisible().catch(() => false);
    
    expect(hasMarketplace || hasCreateAccount, 'At least one main navigation element should be present').toBe(true);
  });

  test('boundary — verify minimum required elements are present for basic functionality', async () => {
    await page.goto(BASE_URL);
    
    // Verify the page has essential AWS branding and functionality
    await expect(page, 'Page should contain AWS branding in URL').toHaveURL(/aws\.amazon\.com/);
    
    // Count available interactive elements
    let interactiveElementCount = 0;
    
    const acceptButton = page.getByRole('button', { name: 'Accept' });
    if (await acceptButton.isVisible().catch(() => false)) {
      interactiveElementCount++;
    }
    
    const declineButton = page.getByRole('button', { name: 'Decline' });
    if (await declineButton.isVisible().catch(() => false)) {
      interactiveElementCount++;
    }
    
    const customizeButton = page.getByRole('button', { name: 'Customize' });
    if (await customizeButton.isVisible().catch(() => false)) {
      interactiveElementCount++;
    }
    
    const cancelButton = page.getByRole('button', { name: 'Cancel' });
    if (await cancelButton.isVisible().catch(() => false)) {
      interactiveElementCount++;
    }
    
    const marketplaceLink = page.getByRole('link', { name: 'AWS Marketplace' });
    if (await marketplaceLink.isVisible().catch(() => false)) {
      interactiveElementCount++;
    }
    
    const createAccountButton = page.getByRole('button', { name: 'Create an AWS account' });
    if (await createAccountButton.isVisible().catch(() => false)) {
      interactiveElementCount++;
    }
    
    expect(interactiveElementCount, 'Page should have at least one interactive element for basic functionality').toBeGreaterThanOrEqual(1);
  });
});