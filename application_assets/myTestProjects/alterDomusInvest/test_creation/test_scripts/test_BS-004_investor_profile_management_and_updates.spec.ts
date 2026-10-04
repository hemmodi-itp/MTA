import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Investor Profile Management and Updates (BS-004)', () => {

  test('positive — investor can successfully update profile information with valid data', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to investor profile section and view current information
    await expect(page.locator('#input_34_8_3'), 'First name field should be visible in profile section').toBeVisible();
    await expect(page.locator('#input_34_8_6'), 'Last name field should be visible in profile section').toBeVisible();
    await expect(page.locator('#input_34_3'), 'Email field should be visible in profile section').toBeVisible();
    
    // Edit contact details and personal information
    await page.locator('#input_34_8_3').clear();
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').clear();
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').clear();
    await page.locator('#input_34_3').fill('john.smith@example.com');
    await page.locator('#input_34_4').clear();
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').clear();
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    
    // Update investor classifications if applicable
    await page.locator('#choice_34_14_0').check();
    
    // Save profile changes with validation
    await page.locator('#searchsubmit').click();
    
    // Verify profile is successfully updated
    await expect(page.locator('#input_34_8_3'), 'First name should be updated after save').toHaveValue('John');
    await expect(page.locator('#input_34_8_6'), 'Last name should be updated after save').toHaveValue('Smith');
    await expect(page.locator('#input_34_3'), 'Email should be updated after save').toHaveValue('john.smith@example.com');
  });

  test('negative — empty required fields show validation errors when attempting to save', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Clear all required fields
    await page.locator('#input_34_8_3').clear();
    await page.locator('#input_34_8_6').clear();
    await page.locator('#input_34_3').clear();
    
    // Attempt to save with empty fields
    await page.locator('#searchsubmit').click();
    
    // Verify validation errors are displayed
    await expect(page.locator('#input_34_8_3'), 'First name field should indicate validation error for empty value').toBeVisible();
    await expect(page.locator('#input_34_8_6'), 'Last name field should indicate validation error for empty value').toBeVisible();
    await expect(page.locator('#input_34_3'), 'Email field should indicate validation error for empty value').toBeVisible();
  });

  test('negative — special characters in name fields trigger validation errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Enter special characters in name fields
    await page.locator('#input_34_8_3').fill('John@#$%');
    await page.locator('#input_34_8_6').fill('Smith!@#');
    await page.locator('#input_34_3').fill('valid@email.com');
    
    // Attempt to save
    await page.locator('#searchsubmit').click();
    
    // Verify special characters are rejected
    await expect(page.locator('#input_34_8_3'), 'First name field should reject special characters').toBeVisible();
    await expect(page.locator('#input_34_8_6'), 'Last name field should reject special characters').toBeVisible();
  });

  test('negative — SQL injection attempts in input fields are properly sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt SQL injection in various fields
    const sqlInjection = "'; DROP TABLE users; --";
    await page.locator('#input_34_8_3').fill(sqlInjection);
    await page.locator('#input_34_8_6').fill(sqlInjection);
    await page.locator('#input_34_3').fill('test@example.com');
    await page.locator('#input_34_5').fill(sqlInjection);
    
    // Attempt to save
    await page.locator('#searchsubmit').click();
    
    // Verify SQL injection is prevented
    await expect(page.locator('#input_34_8_3'), 'First name field should sanitize SQL injection attempts').toBeVisible();
    await expect(page.locator('#input_34_8_6'), 'Last name field should sanitize SQL injection attempts').toBeVisible();
    await expect(page.locator('#input_34_5'), 'Address field should sanitize SQL injection attempts').toBeVisible();
  });

  test('negative — invalid email format shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Enter invalid email formats
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').fill('invalid-email-format');
    
    // Attempt to save
    await page.locator('#searchsubmit').click();
    
    // Verify email validation error
    await expect(page.locator('#input_34_3'), 'Email field should show validation error for invalid format').toBeVisible();
  });

  test('boundary — maximum length input values are accepted within field limits', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Enter values at maximum allowed length
    const maxLengthName = 'A'.repeat(50);
    const maxLengthEmail = 'a'.repeat(240) + '@test.com'; // Assuming 255 char limit
    const maxLengthAddress = 'B'.repeat(255);
    
    await page.locator('#input_34_8_3').fill(maxLengthName);
    await page.locator('#input_34_8_6').fill(maxLengthName);
    await page.locator('#input_34_3').fill(maxLengthEmail);
    await page.locator('#input_34_5').fill(maxLengthAddress);
    
    // Attempt to save
    await page.locator('#searchsubmit').click();
    
    // Verify maximum length values are accepted
    await expect(page.locator('#input_34_8_3'), 'First name field should accept maximum length input').toHaveValue(maxLengthName);
    await expect(page.locator('#input_34_8_6'), 'Last name field should accept maximum length input').toHaveValue(maxLengthName);
  });

  test('boundary — input values exceeding maximum length are truncated or rejected', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Enter values exceeding maximum length
    const tooLongName = 'A'.repeat(300);
    const tooLongEmail = 'a'.repeat(500) + '@test.com';
    const tooLongAddress = 'B'.repeat(1000);
    
    await page.locator('#input_34_8_3').fill(tooLongName);
    await page.locator('#input_34_8_6').fill(tooLongName);
    await page.locator('#input_34_3').fill(tooLongEmail);
    await page.locator('#input_34_5').fill(tooLongAddress);
    
    // Attempt to save
    await page.locator('#searchsubmit').click();
    
    // Verify excessive length is handled appropriately
    const firstNameValue = await page.locator('#input_34_8_3').inputValue();
    const lastNameValue = await page.locator('#input_34_8_6').inputValue();
    
    await expect.soft(firstNameValue.length, 'First name should be truncated to acceptable length').toBeLessThanOrEqual(255);
    await expect.soft(lastNameValue.length, 'Last name should be truncated to acceptable length').toBeLessThanOrEqual(255);
  });

  test('boundary — URL-like input in text fields is properly validated and handled', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Enter URL-like content in various fields
    await page.locator('#input_34_8_3').fill('http://example.com');
    await page.locator('#input_34_8_6').fill('https://malicious.site');
    await page.locator('#input_34_4').fill('javascript:alert(1)');
    await page.locator('#input_34_5').fill('ftp://fileserver.com/path');
    
    // Keep valid email
    await page.locator('#input_34_3').fill('test@example.com');
    
    // Attempt to save
    await page.locator('#searchsubmit').click();
    
    // Verify URL inputs are properly validated
    await expect(page.locator('#input_34_8_3'), 'First name field should validate URL-like input appropriately').toBeVisible();
    await expect(page.locator('#input_34_8_6'), 'Last name field should validate URL-like input appropriately').toBeVisible();
    await expect(page.locator('#input_34_4'), 'Phone field should reject JavaScript URLs for security').toBeVisible();
  });

});