import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Investment Report Generation and Access (BS-006)', () => {
  
  test('positive — complete investment report generation and publication workflow', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to reporting section
    await page.getByRole('link', { name: 'Reports' }).click();
    await expect(page.getByText('Investment Reports'), 'Investment Reports section must be visible').toBeVisible();
    
    // Generate investor statements
    await page.getByRole('button', { name: 'Generate Statements' }).click();
    await page.getByPlaceholder('Select Reporting Period').click();
    await page.getByText('Q4 2023').click();
    await page.getByRole('button', { name: 'Generate' }).click();
    await expect(page.getByText('Investor statements generated successfully'), 'Investor statements generation success message must appear').toBeVisible();
    
    // Generate capital account reports
    await page.getByRole('button', { name: 'Capital Account Reports' }).click();
    await page.getByRole('button', { name: 'Generate Report' }).click();
    await expect(page.getByText('Capital account reports generated'), 'Capital account reports success message must appear').toBeVisible();
    
    // Generate commitment and distribution reports
    await page.getByRole('button', { name: 'Commitment & Distribution' }).click();
    await page.getByRole('button', { name: 'Generate Report' }).click();
    await expect(page.getByText('Commitment and distribution reports generated'), 'Commitment and distribution reports success message must appear').toBeVisible();
    
    // Validate report accuracy
    await page.getByRole('button', { name: 'Validate Reports' }).click();
    await expect(page.getByText('All reports validated successfully'), 'Report validation success message must appear').toBeVisible();
    
    // Publish reports to investor portal
    await page.getByRole('button', { name: 'Publish to Portal' }).click();
    await page.getByRole('button', { name: 'Confirm Publication' }).click();
    await expect(page.getByText('Reports published to investor portal'), 'Report publication success message must appear').toBeVisible();
    
    // Verify secure downloadable access
    await page.getByRole('link', { name: 'Investor Portal' }).click();
    await expect(page.getByText('Available Reports'), 'Available Reports section must be visible in investor portal').toBeVisible();
    await expect(page.getByRole('button', { name: 'Download' }), 'Download button must be available for investors').toBeVisible();
  });

  test('negative — report generation with empty reporting period fails', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Generate Statements' }).click();
    await page.getByPlaceholder('Select Reporting Period').fill('');
    await page.getByRole('button', { name: 'Generate' }).click();
    
    await expect(page.getByText('Reporting period is required'), 'Empty reporting period error message must appear').toBeVisible();
    await expect(page.getByText('Investor statements generated successfully'), 'Success message must not appear for empty input').not.toBeVisible();
  });

  test('negative — report generation with special characters in period field fails', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Generate Statements' }).click();
    await page.getByPlaceholder('Select Reporting Period').fill('!@#$%^&*()');
    await page.getByRole('button', { name: 'Generate' }).click();
    
    await expect(page.getByText('Invalid reporting period format'), 'Special characters validation error must appear').toBeVisible();
    await expect(page.getByText('Investor statements generated successfully'), 'Success message must not appear for invalid input').not.toBeVisible();
  });

  test('negative — SQL injection attempt in report parameters is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Capital Account Reports' }).click();
    await page.getByPlaceholder('Fund ID').fill("'; DROP TABLE investments; --");
    await page.getByRole('button', { name: 'Generate Report' }).click();
    
    await expect(page.getByText('Invalid fund ID format'), 'SQL injection protection error message must appear').toBeVisible();
    await expect(page.getByText('Capital account reports generated'), 'Success message must not appear for SQL injection attempt').not.toBeVisible();
  });

  test('negative — malformed date format in reporting period is rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Commitment & Distribution' }).click();
    await page.getByPlaceholder('Start Date').fill('invalid-date-format');
    await page.getByPlaceholder('End Date').fill('another-invalid-date');
    await page.getByRole('button', { name: 'Generate Report' }).click();
    
    await expect(page.getByText('Please enter valid date format'), 'Invalid date format error message must appear').toBeVisible();
    await expect(page.getByText('Commitment and distribution reports generated'), 'Success message must not appear for invalid date format').not.toBeVisible();
  });

  test('boundary — report generation at maximum allowed reporting periods', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Generate Statements' }).click();
    
    // Test maximum number of reporting periods (boundary condition)
    const maxPeriods = 'Q1 2020,Q2 2020,Q3 2020,Q4 2020,Q1 2021,Q2 2021,Q3 2021,Q4 2021,Q1 2022,Q2 2022,Q3 2022,Q4 2022,Q1 2023,Q2 2023,Q3 2023,Q4 2023';
    await page.getByPlaceholder('Select Reporting Period').fill(maxPeriods);
    await page.getByRole('button', { name: 'Generate' }).click();
    
    await expect(page.getByText('Processing multiple reporting periods'), 'Boundary condition processing message must appear').toBeVisible();
  });

  test('boundary — extremely long fund name in report parameters', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Capital Account Reports' }).click();
    
    const longFundName = 'A'.repeat(255);
    await page.getByPlaceholder('Fund Name').fill(longFundName);
    await page.getByRole('button', { name: 'Generate Report' }).click();
    
    await expect(page.getByText('Fund name exceeds maximum length'), 'Long fund name validation error must appear').toBeVisible();
  });

  test('boundary — URL input in report description field', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Reports' }).click();
    await page.getByRole('button', { name: 'Generate Statements' }).click();
    
    await page.getByPlaceholder('Report Description').fill('https://malicious-site.com/exploit');
    await page.getByPlaceholder('Select Reporting Period').fill('Q4 2023');
    await page.getByRole('button', { name: 'Generate' }).click();
    
    await expect(page.getByText('URL content not allowed in description'), 'URL validation error in description field must appear').toBeVisible();
  });
});