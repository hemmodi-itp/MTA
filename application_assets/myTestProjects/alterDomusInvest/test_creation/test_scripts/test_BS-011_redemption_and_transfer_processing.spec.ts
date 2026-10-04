import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Redemption and Transfer Processing (BS-011)', () => {
  
  test('positive — valid redemption request is processed successfully with complete audit trail', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to transfer agency module
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await expect(page.getByText('Transfer Agency'), 'Transfer Agency page should be displayed').toBeVisible();
    
    // Access redemption processing
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    await expect(page.getByText('Redemption Processing'), 'Redemption processing form should be visible').toBeVisible();
    
    // Validate redemption request details
    await page.getByPlaceholder('Investor ID').fill('INV001');
    await page.getByPlaceholder('Fund Code').fill('FUND001');
    await page.getByPlaceholder('Redemption Amount').fill('50000.00');
    await page.getByPlaceholder('Request Date').fill('2024-01-15');
    
    // Verify investor account balance
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Request Valid'), 'Request validation should pass for sufficient balance').toBeVisible();
    await expect(page.getByText('Available Balance: $100,000.00'), 'Investor balance should be displayed').toBeVisible();
    
    // Process redemption through transfer agency workflow
    await page.getByRole('button', { name: 'Process Redemption' }).click();
    await expect(page.getByText('Processing...'), 'Processing indicator should be shown').toBeVisible();
    
    // Verify workflow completion
    await expect(page.getByText('Redemption Processed Successfully'), 'Success message should appear after processing').toBeVisible();
    
    // Check updated investor positions and capital balances
    await page.getByRole('button', { name: 'View Updated Positions' }).click();
    await expect(page.getByText('Updated Position: $50,000.00'), 'Updated investor position should be displayed').toBeVisible();
    await expect(page.getByText('Transaction ID: RDM'), 'Transaction ID should be generated').toBeVisible();
    
    // Generate and verify transaction confirmation
    await page.getByRole('button', { name: 'Generate Confirmation' }).click();
    await expect(page.getByText('Confirmation Generated'), 'Transaction confirmation should be generated').toBeVisible();
    await expect(page.getByText('Confirmation Number:'), 'Confirmation number should be displayed').toBeVisible();
    
    // Verify audit log creation
    await page.getByRole('button', { name: 'View Audit Log' }).click();
    await expect(page.getByText('Audit Log Entry Created'), 'Audit log entry should be created').toBeVisible();
    await expect(page.getByText('User: Fund Administrator'), 'User information should be logged').toBeVisible();
    await expect(page.getByText('Action: Redemption Processed'), 'Action type should be logged').toBeVisible();
  });

  test('positive — valid transfer between accounts is processed with proper workflow controls', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to transfer processing
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Transfers' }).click();
    
    // Fill transfer details
    await page.getByPlaceholder('From Account').fill('ACC001');
    await page.getByPlaceholder('To Account').fill('ACC002');
    await page.getByPlaceholder('Transfer Amount').fill('25000.00');
    
    // Validate and process transfer
    await page.getByRole('button', { name: 'Validate Transfer' }).click();
    await expect(page.getByText('Transfer Valid'), 'Transfer validation should pass').toBeVisible();
    
    await page.getByRole('button', { name: 'Execute Transfer' }).click();
    await expect(page.getByText('Transfer Completed Successfully'), 'Transfer should complete successfully').toBeVisible();
    
    // Verify audit trail
    await page.getByRole('button', { name: 'View Audit Log' }).click();
    await expect(page.getByText('Transfer Audit Log'), 'Transfer audit log should be accessible').toBeVisible();
  });

  test('negative — redemption request with empty investor ID shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    
    // Submit with empty investor ID
    await page.getByPlaceholder('Investor ID').fill('');
    await page.getByPlaceholder('Fund Code').fill('FUND001');
    await page.getByPlaceholder('Redemption Amount').fill('50000.00');
    
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Investor ID is required'), 'Validation error should appear for empty investor ID').toBeVisible();
    await expect(page.getByRole('button', { name: 'Process Redemption' }), 'Process button should remain disabled').toBeDisabled();
  });

  test('negative — redemption amount with special characters is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    
    // Enter special characters in amount field
    await page.getByPlaceholder('Investor ID').fill('INV001');
    await page.getByPlaceholder('Fund Code').fill('FUND001');
    await page.getByPlaceholder('Redemption Amount').fill('$#@%!');
    
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Invalid amount format'), 'Error message should appear for invalid amount format').toBeVisible();
    await expect(page.getByText('Request Invalid'), 'Request should be marked as invalid').toBeVisible();
  });

  test('negative — SQL injection attempt in fund code field is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    
    // Attempt SQL injection
    await page.getByPlaceholder('Investor ID').fill('INV001');
    await page.getByPlaceholder('Fund Code').fill("'; DROP TABLE funds; --");
    await page.getByPlaceholder('Redemption Amount').fill('50000.00');
    
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Invalid fund code format'), 'SQL injection should be blocked with validation error').toBeVisible();
    await expect(page.getByText('Security violation detected'), 'Security warning should be displayed').toBeVisible();
  });

  test('negative — transfer with insufficient balance is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Transfers' }).click();
    
    // Request transfer exceeding available balance
    await page.getByPlaceholder('From Account').fill('ACC003');
    await page.getByPlaceholder('To Account').fill('ACC004');
    await page.getByPlaceholder('Transfer Amount').fill('999999999.00');
    
    await page.getByRole('button', { name: 'Validate Transfer' }).click();
    await expect(page.getByText('Insufficient balance'), 'Insufficient balance error should be displayed').toBeVisible();
    await expect(page.getByText('Available: $10,000.00'), 'Available balance should be shown').toBeVisible();
    await expect(page.getByRole('button', { name: 'Execute Transfer' }), 'Transfer execution should be blocked').toBeDisabled();
  });

  test('boundary — redemption amount at maximum allowed limit is accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    
    // Test maximum redemption amount (assuming 999,999,999.99 is the limit)
    await page.getByPlaceholder('Investor ID').fill('INV001');
    await page.getByPlaceholder('Fund Code').fill('FUND001');
    await page.getByPlaceholder('Redemption Amount').fill('999999999.99');
    
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Amount at maximum limit'), 'Maximum amount warning should be displayed').toBeVisible();
    await expect(page.getByRole('button', { name: 'Process Redemption' }), 'Processing should still be allowed at maximum limit').toBeEnabled();
  });

  test('boundary — investor ID at maximum length is processed correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    
    // Test maximum length investor ID (assuming 50 characters is the limit)
    const maxLengthInvestorId = 'A'.repeat(50);
    await page.getByPlaceholder('Investor ID').fill(maxLengthInvestorId);
    await page.getByPlaceholder('Fund Code').fill('FUND001');
    await page.getByPlaceholder('Redemption Amount').fill('10000.00');
    
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Investor ID accepted'), 'Maximum length investor ID should be accepted').toBeVisible();
    await expect(page.locator('[name="investorId"]'), 'Full investor ID should be preserved').toHaveValue(maxLengthInvestorId);
  });

  test('boundary — fund code exceeding maximum length is truncated', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Transfer Agency' }).click();
    await page.getByRole('button', { name: 'Process Redemptions' }).click();
    
    // Test fund code exceeding maximum length (assuming 20 characters is the limit)
    const tooLongFundCode = 'FUND' + 'X'.repeat(50);
    await page.getByPlaceholder('Investor ID').fill('INV001');
    await page.getByPlaceholder('Fund Code').fill(tooLongFundCode);
    await page.getByPlaceholder('Redemption Amount').fill('10000.00');
    
    await page.getByRole('button', { name: 'Validate Request' }).click();
    await expect(page.getByText('Fund code too long'), 'Error should appear for oversized fund code').toBeVisible();
    await expect(page.getByText('Maximum 20 characters allowed'), 'Character limit message should be displayed').toBeVisible();
  });