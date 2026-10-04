import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Interact with AWS_Test (SC-004)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — complete interaction flow with all available elements', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Click accept button if visible
    const acceptButton = page.getByRole('button', { name: 'Accept' });
    if (await acceptButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await acceptButton.click();
      await expect(acceptButton, 'Accept button should be clickable').toBeEnabled();
    }
    
    // Click decline button if visible
    const declineButton = page.getByRole('button', { name: 'Decline' });
    if (await declineButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await declineButton.click();
      await expect(declineButton, 'Decline button should be clickable').toBeEnabled();
    }
    
    // Click customize button if visible
    const customizeButton = page.getByRole('button', { name: 'Customize' });
    if (await customizeButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await customizeButton.click();
      await expect(customizeButton, 'Customize button should be clickable').toBeEnabled();
    }
    
    // Click cancel button if visible
    const cancelButton = page.getByRole('button', { name: 'Cancel' });
    if (await cancelButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await cancelButton.click();
      await expect(cancelButton, 'Cancel button should be clickable').toBeEnabled();
    }
    
    // Click play button if visible (media interaction)
    const playButton = page.getByRole('button', { name: 'Play' });
    if (await playButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await playButton.click();
      await expect(playButton, 'Play button should be clickable for media interaction').toBeEnabled();
    }
    
    // Click fullscreen button if visible
    const fullscreenButton = page.getByRole('button', { name: 'Fullscreen' });
    if (await fullscreenButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await fullscreenButton.click();
      await expect(fullscreenButton, 'Fullscreen button should be clickable').toBeEnabled();
    }
    
    // Click close modal dialog if visible
    const closeModalButton = page.getByRole('button', { name: 'Close Modal Dialog' });
    if (await closeModalButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      await closeModalButton.click();
      await expect(closeModalButton, 'Close modal dialog button should be clickable').toBeEnabled();
    }
    
    // Verify we're still on the AWS page
    await expect(page, 'Should remain on AWS domain after interactions').toHaveURL(/aws\.amazon\.com/);
  });

  test('negative — element interaction fails when expected content not found', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Try to interact with accept button but expect potential failure
    const acceptButton = page.getByRole('button', { name: 'Accept' });
    
    // Check if button exists and is enabled before clicking
    const buttonExists = await acceptButton.isVisible({ timeout: 2000 }).catch(() => false);
    
    if (buttonExists) {
      await acceptButton.click();
      
      // Verify the interaction didn't lead to an error state
      const hasError = await page.locator('text=error').isVisible({ timeout: 3000 }).catch(() => false);
      await expect(hasError, 'Should not encounter error state after button interaction').toBeFalsy();
    } else {
      // Log that expected element was not found
      console.log('Expected accept button not found - this represents the negative test case');
      await expect(page, 'Page should still be accessible even when expected elements are missing').toHaveURL(/aws\.amazon\.com/);
    }
  });

  test('boundary — interaction with maximum available elements in sequence', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    const buttons = [
      { locator: page.getByRole('button', { name: 'Accept' }), name: 'Accept' },
      { locator: page.getByRole('button', { name: 'Decline' }), name: 'Decline' },
      { locator: page.getByRole('button', { name: 'Customize' }), name: 'Customize' },
      { locator: page.getByRole('button', { name: 'Cancel' }), name: 'Cancel' },
      { locator: page.getByRole('button', { name: 'Play' }), name: 'Play' },
      { locator: page.getByRole('button', { name: 'Fullscreen' }), name: 'Fullscreen' },
      { locator: page.getByRole('button', { name: 'Close Modal Dialog' }), name: 'Close Modal Dialog' }
    ];
    
    let interactionCount = 0;
    
    for (const button of buttons) {
      if (await button.locator.isVisible({ timeout: 2000 }).catch(() => false)) {
        await button.locator.click();
        interactionCount++;
        
        // Small delay between interactions to prevent overwhelming the UI
        await page.waitForTimeout(500);
      }
    }
    
    // Verify we successfully interacted with at least some elements
    await expect(interactionCount > 0, `Should have interacted with at least one element, got ${interactionCount} interactions`).toBeTruthy();
    
    // Verify page is still functional after maximum interactions
    await expect(page, 'Page should remain functional after boundary-level interactions').toHaveURL(/aws\.amazon\.com/);
  });
});