import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Compliance Review and Approval Workflow (BS-002)', () => {

  test('positive — compliance officer successfully reviews and approves investor onboarding application', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to compliance dashboard
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await expect(page.getByText('Pending Applications'), 'Compliance dashboard should show pending applications section').toBeVisible();
    
    // Select pending application for review
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    await expect(page.getByText('Application Review'), 'Application review page should be displayed').toBeVisible();
    
    // Validate mandatory information is complete
    await page.getByRole('button', { name: 'Validate Information' }).click();
    await expect(page.getByText('All mandatory fields completed'), 'Validation should confirm all mandatory fields are complete').toBeVisible();
    
    // Perform KYC review workflow
    await page.getByRole('button', { name: 'Start KYC Review' }).click();
    await page.getByRole('combobox', { name: 'KYC Status' }).selectOption('Approved');
    await page.getByPlaceholder('KYC Review Comments').fill('Identity verification documents approved. All checks passed.');
    await page.getByRole('button', { name: 'Complete KYC Review' }).click();
    await expect(page.getByText('KYC Review Completed'), 'KYC review should be marked as completed').toBeVisible();
    
    // Perform AML review and sanctions screening
    await page.getByRole('button', { name: 'Start AML Screening' }).click();
    await page.getByRole('combobox', { name: 'AML Status' }).selectOption('Clear');
    await page.getByPlaceholder('AML Review Comments').fill('No matches found in sanctions lists. Risk assessment: Low.');
    await page.getByRole('button', { name: 'Complete AML Review' }).click();
    await expect(page.getByText('AML Screening Completed'), 'AML screening should be marked as completed').toBeVisible();
    
    // Approve the onboarding application
    await page.getByRole('combobox', { name: 'Final Decision' }).selectOption('Approved');
    await page.getByPlaceholder('Final Decision Comments').fill('All compliance checks passed. Application approved for onboarding.');
    await page.getByRole('button', { name: 'Submit Decision' }).click();
    
    // Verify approval and audit trail generation
    await expect(page.getByText('Application Approved'), 'Application should be marked as approved').toBeVisible();
    await expect(page.getByText('Audit trail generated'), 'Audit trail should be automatically generated').toBeVisible();
    await page.getByRole('button', { name: 'View Audit Trail' }).click();
    await expect(page.getByText('KYC Review: Approved'), 'Audit trail should show KYC review decision').toBeVisible();
    await expect(page.getByText('AML Screening: Clear'), 'Audit trail should show AML screening result').toBeVisible();
  });

  test('negative — empty KYC review comments field shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    
    await page.getByRole('button', { name: 'Start KYC Review' }).click();
    await page.getByRole('combobox', { name: 'KYC Status' }).selectOption('Approved');
    await page.getByRole('button', { name: 'Complete KYC Review' }).click();
    
    await expect(page.getByText('KYC comments are required'), 'Empty KYC comments should trigger validation error').toBeVisible();
    await expect(page.getByText('KYC Review Completed'), 'KYC review should not be completed without comments').not.toBeVisible();
  });

  test('negative — special characters in review comments cause validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    
    await page.getByRole('button', { name: 'Start AML Screening' }).click();
    await page.getByRole('combobox', { name: 'AML Status' }).selectOption('Clear');
    await page.getByPlaceholder('AML Review Comments').fill('<script>alert("xss")</script>');
    await page.getByRole('button', { name: 'Complete AML Review' }).click();
    
    await expect(page.getByText('Invalid characters in comments field'), 'Special characters should trigger validation error').toBeVisible();
    await expect(page.getByText('AML Screening Completed'), 'AML review should not complete with invalid characters').not.toBeVisible();
  });

  test('negative — SQL injection attempt in search field is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByPlaceholder('Search Applications').fill("'; DROP TABLE applications; --");
    await page.getByRole('button', { name: 'Search' }).click();
    
    await expect(page.getByText('Invalid search criteria'), 'SQL injection attempt should be blocked').toBeVisible();
    await expect(page.getByText('Pending Applications'), 'Applications table should still be accessible').toBeVisible();
  });

  test('negative — wrong status format selection prevents workflow completion', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    
    // Attempt to submit with invalid status combination
    await page.getByRole('button', { name: 'Start KYC Review' }).click();
    await page.getByRole('combobox', { name: 'KYC Status' }).selectOption('Rejected');
    await page.getByPlaceholder('KYC Review Comments').fill('Valid comment');
    await page.getByRole('button', { name: 'Complete KYC Review' }).click();
    
    await page.getByRole('button', { name: 'Start AML Screening' }).click();
    await page.getByRole('combobox', { name: 'AML Status' }).selectOption('Clear');
    await page.getByRole('combobox', { name: 'Final Decision' }).selectOption('Approved');
    await page.getByRole('button', { name: 'Submit Decision' }).click();
    
    await expect(page.getByText('Cannot approve application with rejected KYC'), 'Conflicting status selections should show error').toBeVisible();
  });

  test('boundary — review comments at maximum character limit are accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthComment = 'A'.repeat(1000);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    
    await page.getByRole('button', { name: 'Start KYC Review' }).click();
    await page.getByRole('combobox', { name: 'KYC Status' }).selectOption('Approved');
    await page.getByPlaceholder('KYC Review Comments').fill(maxLengthComment);
    await page.getByRole('button', { name: 'Complete KYC Review' }).click();
    
    await expect(page.getByText('KYC Review Completed'), 'Maximum length comments should be accepted').toBeVisible();
  });

  test('boundary — review comments exceeding character limit show validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongComment = 'A'.repeat(1001);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    
    await page.getByRole('button', { name: 'Start AML Screening' }).click();
    await page.getByRole('combobox', { name: 'AML Status' }).selectOption('Clear');
    await page.getByPlaceholder('AML Review Comments').fill(tooLongComment);
    await page.getByRole('button', { name: 'Complete AML Review' }).click();
    
    await expect(page.getByText('Comments exceed maximum length of 1000 characters'), 'Comments exceeding limit should show validation error').toBeVisible();
    await expect(page.getByText('AML Screening Completed'), 'Review should not complete with oversized comments').not.toBeVisible();
  });

  test('boundary — URL input in comments field is properly sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Compliance Dashboard' }).click();
    await page.getByRole('button', { name: 'Review Application' }).first().click();
    
    await page.getByRole('button', { name: 'Start KYC Review' }).click();
    await page.getByRole('combobox', { name: 'KYC Status' }).selectOption('Approved');
    await page.getByPlaceholder('KYC Review Comments').fill('Documentation verified at https://example.com/docs');
    await page.getByRole('button', { name: 'Complete KYC Review' }).click();
    
    await expect(page.getByText('KYC Review Completed'), 'URL input should be sanitized and accepted').toBeVisible();
    
    await page.getByRole('button', { name: 'View Audit Trail' }).click();
    await expect(page.getByText('Documentation verified at [URL_SANITIZED]'), 'URL should be sanitized in audit trail').toBeVisible();
  });

});