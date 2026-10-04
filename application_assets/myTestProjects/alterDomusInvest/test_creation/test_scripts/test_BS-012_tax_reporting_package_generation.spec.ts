import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Tax Reporting Package Generation (BS-012)', () => {
  test('positive — complete tax reporting package generation workflow succeeds', async ({ page }) => {
    await page.goto(BASE_URL);

    // Navigate to tax reporting section
    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await expect(page.getByText('Tax Reporting Package Generation'), 'Tax reporting page header should be visible').toBeVisible();

    // Select tax period
    await page.getByPlaceholder('Select Tax Period').click();
    await page.getByText('2023 Tax Year').click();
    await expect(page.getByPlaceholder('Select Tax Period'), 'Tax period should be selected').toHaveValue('2023 Tax Year');

    // Gather investor transaction data
    await page.getByRole('button', { name: 'Gather Transaction Data' }).click();
    await expect(page.getByText('Transaction data gathering completed'), 'Transaction data gathering confirmation should appear').toBeVisible();

    // Generate tax packages
    await page.getByRole('button', { name: 'Generate Tax Packages' }).click();
    await expect(page.getByText('Generating tax packages...'), 'Generation progress indicator should be visible').toBeVisible();
    
    // Wait for generation completion
    await expect(page.getByText('Tax packages generated successfully'), 'Generation success message should appear').toBeVisible({ timeout: 30000 });

    // Validate tax calculations
    await page.getByRole('button', { name: 'Validate Calculations' }).click();
    await expect(page.getByText('Tax calculations validated'), 'Validation confirmation should appear').toBeVisible();

    // Review and approve reports
    await page.getByRole('button', { name: 'Review Reports' }).click();
    await expect(page.getByRole('button', { name: 'Approve All Reports' }), 'Approve button should be available').toBeVisible();
    
    await page.getByRole('button', { name: 'Approve All Reports' }).click();
    await expect(page.getByText('All tax reports approved'), 'Approval confirmation should appear').toBeVisible();

    // Publish to investor portal
    await page.getByRole('button', { name: 'Publish to Portal' }).click();
    await expect(page.getByText('Tax packages published successfully'), 'Publishing confirmation should appear').toBeVisible();

    // Enable secure download access
    await page.getByRole('button', { name: 'Enable Download Access' }).click();
    await expect(page.getByText('Secure download access enabled'), 'Download access confirmation should appear').toBeVisible();

    // Verify final status
    await expect(page.getByText('Status: Available for Download'), 'Final status should show available for download').toBeVisible();
  });

  test('negative — empty tax period selection shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await expect(page.getByText('Tax Reporting Package Generation'), 'Tax reporting page should load').toBeVisible();

    // Attempt to generate without selecting tax period
    await page.getByRole('button', { name: 'Gather Transaction Data' }).click();
    
    await expect(page.getByText('Please select a tax period'), 'Empty tax period validation error should appear').toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate Tax Packages' }), 'Generate button should remain disabled').toBeDisabled();
  });

  test('negative — special characters in investor filter cause error', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await page.getByPlaceholder('Select Tax Period').click();
    await page.getByText('2023 Tax Year').click();

    // Enter special characters in investor filter
    await page.getByPlaceholder('Filter Investors').fill('!@#$%^&*()');
    await page.getByRole('button', { name: 'Apply Filter' }).click();

    await expect(page.getByText('Invalid characters in investor filter'), 'Special characters error message should appear').toBeVisible();
    await expect(page.getByRole('button', { name: 'Gather Transaction Data' }), 'Transaction data button should be disabled').toBeDisabled();
  });

  test('negative — SQL injection attempt in search field is blocked', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await page.getByPlaceholder('Select Tax Period').click();
    await page.getByText('2023 Tax Year').click();

    // Attempt SQL injection
    await page.getByPlaceholder('Search Reports').fill("'; DROP TABLE investors; --");
    await page.getByRole('button', { name: 'Search' }).click();

    await expect(page.getByText('Invalid search query format'), 'SQL injection protection error should appear').toBeVisible();
    await expect(page.getByText('Security incident logged'), 'Security logging message should appear').toBeVisible();
  });

  test('negative — wrong date format in custom period shows format error', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await page.getByRole('button', { name: 'Custom Period' }).click();

    // Enter wrong date format
    await page.getByPlaceholder('Start Date').fill('32/13/2023');
    await page.getByPlaceholder('End Date').fill('invalid-date');
    await page.getByRole('button', { name: 'Set Period' }).click();

    await expect(page.getByText('Invalid date format'), 'Date format error should appear').toBeVisible();
    await expect(page.getByText('Use MM/DD/YYYY format'), 'Format instruction should be shown').toBeVisible();
  });

  test('boundary — maximum number of investors (1000) can be processed', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await page.getByPlaceholder('Select Tax Period').click();
    await page.getByText('2023 Tax Year').click();

    // Select maximum investor count
    await page.getByRole('button', { name: 'Advanced Options' }).click();
    await page.getByPlaceholder('Max Investors').fill('1000');
    await page.getByRole('button', { name: 'Apply' }).click();

    await expect(page.getByText('1000 investors selected'), 'Maximum investor count should be accepted').toBeVisible();
    
    await page.getByRole('button', { name: 'Gather Transaction Data' }).click();
    await expect(page.getByText('Processing 1000 investors'), 'Processing message should show correct count').toBeVisible();
  });

  test('boundary — report name at maximum length (255 characters) is accepted', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await page.getByPlaceholder('Select Tax Period').click();
    await page.getByText('2023 Tax Year').click();

    const maxLengthName = 'A'.repeat(255);
    await page.getByPlaceholder('Report Package Name').fill(maxLengthName);

    await expect(page.getByPlaceholder('Report Package Name'), 'Maximum length report name should be accepted').toHaveValue(maxLengthName);
    await expect(page.getByText('255/255 characters'), 'Character count should show maximum').toBeVisible();
  });

  test('boundary — report name exceeding maximum length (256 characters) is truncated', async ({ page }) => {
    await page.goto(BASE_URL);

    await page.getByRole('link', { name: 'Tax Reporting' }).click();
    await page.getByPlaceholder('Select Tax Period').click();
    await page.getByText('2023 Tax Year').click();

    const exceedingLengthName = 'A'.repeat(256);
    await page.getByPlaceholder('Report Package Name').fill(exceedingLengthName);

    await expect(page.getByText('Report name too long'), 'Length validation error should appear').toBeVisible();
    await expect(page.getByPlaceholder('Report Package Name'), 'Report name should be truncated to 255 characters').toHaveValue('A'.repeat(255));
  });
});