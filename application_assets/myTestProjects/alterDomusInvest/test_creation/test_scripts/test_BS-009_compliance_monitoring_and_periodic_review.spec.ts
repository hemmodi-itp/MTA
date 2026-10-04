import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Compliance Monitoring and Periodic Review (BS-009)', () => {
  
  test('positive — compliance officer completes full compliance monitoring workflow', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Access compliance dashboard for overview
    await expect(page.getByText('Compliance'), 'Compliance navigation menu should be visible').toBeVisible();
    await page.getByText('Compliance').click();
    await expect(page.getByText('Dashboard'), 'Compliance dashboard link should be available').toBeVisible();
    await page.getByText('Dashboard').click();
    
    // Verify compliance dashboard loads with overview
    await expect(page.getByRole('heading', { name: 'Compliance Overview' }), 'Compliance overview heading should be displayed').toBeVisible();
    await expect(page.getByText('Document Status'), 'Document status section should be present').toBeVisible();
    
    // Review document expiry notifications
    await expect(page.getByText('Expiring Documents'), 'Expiring documents notification section should be visible').toBeVisible();
    await page.getByText('Expiring Documents').click();
    await expect(page.getByText('Documents expiring in next 30 days'), 'Document expiry timeline should be shown').toBeVisible();
    
    // Generate periodic review reminders for investors
    await page.getByRole('button', { name: 'Generate Review Reminders' }).click();
    await expect(page.getByText('Review reminders generated successfully'), 'Success message for review reminders should appear').toBeVisible();
    
    // Monitor sanctions screening results
    await page.getByText('Sanctions Screening').click();
    await expect(page.getByText('Latest Screening Results'), 'Sanctions screening results section should be displayed').toBeVisible();
    await expect(page.getByText('No matches found'), 'Sanctions screening status should be shown').toBeVisible();
    
    // Update compliance status in investor records
    await page.getByRole('button', { name: 'Update Compliance Status' }).click();
    await page.getByRole('combobox', { name: 'Compliance Status' }).selectOption('Compliant');
    await page.getByPlaceholder('Add compliance notes').fill('Periodic review completed - all documents current');
    await page.getByRole('button', { name: 'Save Status' }).click();
    await expect(page.getByText('Compliance status updated successfully'), 'Status update confirmation should be displayed').toBeVisible();
    
    // Generate compliance audit reports
    await page.getByText('Reports').click();
    await page.getByRole('button', { name: 'Generate Audit Report' }).click();
    await page.getByRole('combobox', { name: 'Report Period' }).selectOption('monthly');
    await page.getByRole('button', { name: 'Generate Report' }).click();
    await expect(page.getByText('Audit report generated successfully'), 'Report generation success message should appear').toBeVisible();
    await expect(page.getByText('Download Report'), 'Download link for audit report should be available').toBeVisible();
  });

  test('negative — empty compliance status update shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    await page.getByRole('button', { name: 'Update Compliance Status' }).click();
    
    // Leave status empty and try to save
    await page.getByPlaceholder('Add compliance notes').fill('');
    await page.getByRole('button', { name: 'Save Status' }).click();
    
    await expect(page.getByText('Compliance status is required'), 'Validation error for empty status should be shown').toBeVisible();
    await expect(page.getByText('Compliance notes are required'), 'Validation error for empty notes should be displayed').toBeVisible();
  });

  test('negative — special characters in compliance notes cause validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    await page.getByRole('button', { name: 'Update Compliance Status' }).click();
    
    await page.getByRole('combobox', { name: 'Compliance Status' }).selectOption('Compliant');
    await page.getByPlaceholder('Add compliance notes').fill('<script>alert("test")</script>');
    await page.getByRole('button', { name: 'Save Status' }).click();
    
    await expect(page.getByText('Invalid characters detected in compliance notes'), 'Special characters validation error should be displayed').toBeVisible();
  });

  test('negative — sql injection attempt in search field is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    
    await page.getByPlaceholder('Search investors').fill("'; DROP TABLE investors; --");
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('Invalid search criteria'), 'SQL injection attempt should be blocked with error message').toBeVisible();
    await expect(page.getByText('No results found'), 'Search should return no results for malicious input').toBeVisible();
  });

  test('negative — invalid date format in report period shows error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    await page.getByText('Reports').click();
    await page.getByRole('button', { name: 'Generate Audit Report' }).click();
    
    await page.getByPlaceholder('Custom date range').fill('invalid-date-format');
    await page.getByRole('button', { name: 'Generate Report' }).click();
    
    await expect(page.getByText('Invalid date format'), 'Date format validation error should be shown').toBeVisible();
    await expect(page.getByText('Please use DD/MM/YYYY format'), 'Date format instruction should be displayed').toBeVisible();
  });

  test('boundary — compliance notes at maximum character limit are accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthNotes = 'A'.repeat(500);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    await page.getByRole('button', { name: 'Update Compliance Status' }).click();
    
    await page.getByRole('combobox', { name: 'Compliance Status' }).selectOption('Compliant');
    await page.getByPlaceholder('Add compliance notes').fill(maxLengthNotes);
    await page.getByRole('button', { name: 'Save Status' }).click();
    
    await expect(page.getByText('Compliance status updated successfully'), 'Maximum length compliance notes should be accepted').toBeVisible();
    await expect(page.getByText('500/500 characters'), 'Character counter should show maximum limit reached').toBeVisible();
  });

  test('boundary — compliance notes exceeding character limit show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongNotes = 'A'.repeat(501);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    await page.getByRole('button', { name: 'Update Compliance Status' }).click();
    
    await page.getByRole('combobox', { name: 'Compliance Status' }).selectOption('Compliant');
    await page.getByPlaceholder('Add compliance notes').fill(tooLongNotes);
    await page.getByRole('button', { name: 'Save Status' }).click();
    
    await expect(page.getByText('Compliance notes exceed maximum length of 500 characters'), 'Character limit validation error should be displayed').toBeVisible();
    await expect(page.getByText('501/500 characters'), 'Character counter should show limit exceeded').toBeVisible();
  });

  test('boundary — url input in document upload field is handled correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByText('Compliance').click();
    await page.getByText('Dashboard').click();
    await page.getByRole('button', { name: 'Upload Compliance Document' }).click();
    
    await page.getByPlaceholder('Document name').fill('https://malicious-site.com/document.pdf');
    await page.getByRole('button', { name: 'Upload' }).click();
    
    await expect(page.getByText('Document name cannot contain URLs'), 'URL validation error should be shown for document name field').toBeVisible();
    await expect(page.getByText('Please provide a valid document name'), 'Document name format instruction should be displayed').toBeVisible();
  });
});