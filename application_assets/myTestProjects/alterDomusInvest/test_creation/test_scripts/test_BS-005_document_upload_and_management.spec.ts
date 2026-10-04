import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Document Upload and Management (BS-005)', () => {
  
  test('positive — complete document upload with categorization and versioning succeeds', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to document management section
    await page.getByRole('link', { name: 'Documents' }).click();
    await expect(page.getByText('Document Management'), 'Document management page should be visible').toBeVisible();
    
    // Select document category for upload
    await page.getByRole('button', { name: 'Upload Document' }).click();
    await expect(page.getByText('Select Category'), 'Category selection should be available').toBeVisible();
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Financial Reports' }).click();
    
    // Upload new document with secure transmission
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput, 'File input should be visible for upload').toBeVisible();
    await fileInput.setInputFiles('test-document.pdf');
    
    // Add document metadata
    await page.getByPlaceholder('Document Title').fill('Q3 Financial Report');
    await page.getByPlaceholder('Description').fill('Quarterly financial report for Q3 2024');
    
    // Submit document upload
    await page.getByRole('button', { name: 'Upload' }).click();
    
    // System automatically versions the document and confirms successful storage
    await expect(page.getByText('Document uploaded successfully'), 'Success message should confirm upload completion').toBeVisible();
    await expect(page.getByText('Version: 1.0'), 'Document should be automatically versioned').toBeVisible();
    await expect(page.getByText('Category: Financial Reports'), 'Document should be properly categorized').toBeVisible();
    
    // Verify document appears in document list
    await expect(page.getByText('Q3 Financial Report'), 'Uploaded document should appear in document list').toBeVisible();
    await expect(page.getByText('Secure'), 'Document should show secure transmission status').toBeVisible();
  });

  test('negative — empty document upload shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    // Try to upload without selecting file or category
    await page.getByRole('button', { name: 'Upload' }).click();
    
    await expect(page.getByText('Please select a file to upload'), 'Error message should appear for missing file').toBeVisible();
    await expect(page.getByText('Document category is required'), 'Error message should appear for missing category').toBeVisible();
  });

  test('negative — invalid file format shows rejection error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Financial Reports' }).click();
    
    // Try to upload unsupported file format
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('test-file.exe');
    await page.getByPlaceholder('Document Title').fill('Invalid File');
    await page.getByRole('button', { name: 'Upload' }).click();
    
    await expect(page.getByText('File format not supported'), 'Error message should reject invalid file format').toBeVisible();
    await expect(page.getByText('Allowed formats: PDF, DOC, DOCX, XLS, XLSX'), 'Supported formats should be listed').toBeVisible();
  });

  test('negative — malicious filename with special characters is sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Legal Documents' }).click();
    
    // Try to upload with malicious filename
    await page.getByPlaceholder('Document Title').fill('../../../etc/passwd<script>alert("xss")</script>');
    await page.getByPlaceholder('Description').fill('SELECT * FROM documents; DROP TABLE users;--');
    
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('test-document.pdf');
    await page.getByRole('button', { name: 'Upload' }).click();
    
    await expect(page.getByText('Invalid characters removed from filename'), 'System should sanitize malicious input').toBeVisible();
    await expect(page.getByText('Document title has been cleaned'), 'Title sanitization message should appear').toBeVisible();
  });

  test('negative — unauthorized category access shows permission error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    // Try to select restricted category
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Confidential Board Minutes' }).click();
    
    await expect(page.getByText('Access denied to this category'), 'Permission error should appear for restricted category').toBeVisible();
    await expect(page.getByText('Contact administrator for access'), 'Help message should guide user').toBeVisible();
  });

  test('boundary — document title at maximum length is accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Reports' }).click();
    
    // Test maximum allowed title length (255 characters)
    const maxLengthTitle = 'A'.repeat(255);
    await page.getByPlaceholder('Document Title').fill(maxLengthTitle);
    
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('test-document.pdf');
    await page.getByRole('button', { name: 'Upload' }).click();
    
    await expect(page.getByText('Document uploaded successfully'), 'Maximum length title should be accepted').toBeVisible();
    await expect(page.locator(`text="${maxLengthTitle.substring(0, 50)}"`), 'Title should be preserved at maximum length').toBeVisible();
  });

  test('boundary — document title exceeding maximum length is truncated', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Reports' }).click();
    
    // Test exceeding maximum title length (256+ characters)
    const tooLongTitle = 'B'.repeat(300);
    await page.getByPlaceholder('Document Title').fill(tooLongTitle);
    
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('test-document.pdf');
    await page.getByRole('button', { name: 'Upload' }).click();
    
    await expect(page.getByText('Title has been truncated to 255 characters'), 'Truncation warning should appear').toBeVisible();
    await expect(page.getByText('Document uploaded successfully'), 'Upload should still succeed after truncation').toBeVisible();
  });

  test('boundary — maximum file size upload is processed correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Documents' }).click();
    await page.getByRole('button', { name: 'Upload Document' }).click();
    
    await page.getByRole('combobox', { name: 'Document Category' }).click();
    await page.getByRole('option', { name: 'Data Files' }).click();
    
    await page.getByPlaceholder('Document Title').fill('Large Test File');
    
    // Simulate large file upload (at size boundary)
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('large-test-file.pdf');
    await page.getByRole('button', { name: 'Upload' }).click();
    
    // Should show processing indicator for large files
    await expect(page.getByText('Processing large file'), 'Processing message should appear for large files').toBeVisible();
    await expect(page.getByRole('progressbar'), 'Progress bar should be visible during upload').toBeVisible();
    
    // Wait for completion with extended timeout for large file
    await expect(page.getByText('Document uploaded successfully'), 'Large file upload should complete successfully').toBeVisible({ timeout: 30000 });
  });

});