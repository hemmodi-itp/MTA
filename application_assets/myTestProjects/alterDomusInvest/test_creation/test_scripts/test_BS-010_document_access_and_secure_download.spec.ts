import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Document Access and Secure Download (BS-010)', () => {

  test('positive — investor successfully navigates, browses documents by category, and downloads with secure transmission', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to document access section
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    // Browse available documents by category
    await page.getByRole('button', { name: 'Category' }).click();
    await page.getByText('Investment Reports').click();
    await expect(page.getByText('Investment Reports'), 'Investment Reports category should be selected').toBeVisible();
    
    // Select document for download
    await page.getByRole('link', { name: 'Q3 2023 Report.pdf' }).click();
    await expect(page.getByText('Document Details'), 'Document details page should load').toBeVisible();
    
    // System validates access permissions and download document securely
    const downloadPromise = page.waitForDownload({ timeout: 10000 });
    await page.getByRole('button', { name: 'Download' }).click();
    const download = await downloadPromise;
    
    await expect.poll(async () => download.suggestedFilename(), 'Downloaded file should have correct name').toBe('Q3 2023 Report.pdf');
    
    // Verify audit trail logging
    await page.getByRole('button', { name: 'Download History' }).click();
    await expect(page.getByText('Q3 2023 Report.pdf'), 'Document access should be logged in download history').toBeVisible();
    await expect(page.getByText('Downloaded'), 'Download status should be recorded').toBeVisible();
  });

  test('negative — empty document search returns appropriate message', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    await page.getByPlaceholder('Search documents').fill('');
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('Please enter search criteria'), 'Empty search should show validation message').toBeVisible();
  });

  test('negative — special characters in document search handle gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    await page.getByPlaceholder('Search documents').fill('!@#$%^&*()');
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('No documents found'), 'Special characters search should return no results message').toBeVisible();
  });

  test('negative — SQL injection attempt in search is prevented', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    await page.getByPlaceholder('Search documents').fill("'; DROP TABLE documents; --");
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('Invalid search query'), 'SQL injection attempt should show security error').toBeVisible();
  });

  test('negative — wrong format file download attempt shows error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('link', { name: 'Corrupted File.exe' }).click();
    await page.getByRole('button', { name: 'Download' }).click();
    
    await expect(page.getByText('File format not supported'), 'Unsupported file format should show error message').toBeVisible();
  });

  test('boundary — search term at maximum length is handled correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    const maxLengthSearch = 'a'.repeat(255);
    await page.getByPlaceholder('Search documents').fill(maxLengthSearch);
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('Search completed'), 'Maximum length search should process successfully').toBeVisible();
  });

  test('boundary — search term exceeding maximum length is truncated', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    const tooLongSearch = 'a'.repeat(300);
    await page.getByPlaceholder('Search documents').fill(tooLongSearch);
    
    const inputValue = await page.getByPlaceholder('Search documents').inputValue();
    await expect.poll(async () => inputValue.length, 'Search input should be truncated to maximum allowed length').toBeLessThanOrEqual(255);
  });

  test('boundary — URL input in document search is sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Library'), 'Document library page should be displayed').toBeVisible();
    
    await page.getByPlaceholder('Search documents').fill('http://malicious-site.com');
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('Invalid search format'), 'URL input should be rejected with appropriate message').toBeVisible();
  });

});