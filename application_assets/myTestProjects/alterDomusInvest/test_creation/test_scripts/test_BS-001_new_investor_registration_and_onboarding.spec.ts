import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('New Investor Registration and Onboarding (BS-001)', () => {
  
  test('positive — complete investor onboarding flow with valid information', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Create new investor account with basic information
    await page.locator('#input_34_278879').fill('INV123456789');
    await expect(page.locator('#input_34_278879'), 'Investor ID field should accept valid identification number').toHaveValue('INV123456789');
    
    await page.locator('#input_34_8_3').fill('John');
    await expect(page.locator('#input_34_8_3'), 'First name field should accept valid name').toHaveValue('John');
    
    await page.locator('#input_34_8_6').fill('Smith');
    await expect(page.locator('#input_34_8_6'), 'Last name field should accept valid name').toHaveValue('Smith');
    
    // Capture complete investor profile details including contact information
    await page.locator('#input_34_3').fill('john.smith@example.com');
    await expect(page.locator('#input_34_3'), 'Email field should accept valid email address').toHaveValue('john.smith@example.com');
    
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await expect(page.locator('#input_34_4'), 'Phone field should accept valid phone number').toHaveValue('+1-555-123-4567');
    
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    await expect(page.locator('#input_34_5'), 'Address field should accept complete address').toHaveValue('123 Main Street, New York, NY 10001');
    
    // Submit onboarding application for review
    await page.locator('#searchsubmit').click();
    await expect(page.getByText('pending'), 'Application should show pending status after submission').toBeVisible();
  });

  test('negative — empty required fields show validation errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Attempt to submit with empty fields
    await page.locator('#searchsubmit').click();
    
    await expect(page.getByText('required'), 'Empty investor ID should show required field validation').toBeVisible();
    await expect(page.getByText('Please enter'), 'Empty required fields should display validation messages').toBeVisible();
  });

  test('negative — special characters in name fields show validation errors', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.locator('#input_34_278879').fill('INV123456789');
    await page.locator('#input_34_8_3').fill('J@hn$');
    await page.locator('#input_34_8_6').fill('Sm!th#');
    await page.locator('#input_34_3').fill('john.smith@example.com');
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    
    await page.locator('#searchsubmit').click();
    
    await expect(page.getByText('invalid characters'), 'Special characters in name fields should show validation error').toBeVisible();
  });

  test('negative — SQL injection attempt in investor ID field is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.locator('#input_34_278879').fill("'; DROP TABLE investors; --");
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').fill('john.smith@example.com');
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    
    await page.locator('#searchsubmit').click();
    
    await expect(page.getByText('invalid format'), 'SQL injection attempt should be blocked with validation error').toBeVisible();
  });

  test('negative — wrong email format shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.locator('#input_34_278879').fill('INV123456789');
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').fill('invalid-email-format');
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    
    await page.locator('#searchsubmit').click();
    
    await expect(page.getByText('valid email'), 'Invalid email format should show validation error message').toBeVisible();
  });

  test('boundary — investor ID at maximum length is accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthId = 'INV' + '1'.repeat(252); // 255 total characters
    await page.locator('#input_34_278879').fill(maxLengthId);
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').fill('john.smith@example.com');
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    
    await expect(page.locator('#input_34_278879'), 'Maximum length investor ID should be accepted').toHaveValue(maxLengthId);
    
    await page.locator('#searchsubmit').click();
    await expect(page.getByText('pending'), 'Form with boundary length investor ID should submit successfully').toBeVisible();
  });

  test('boundary — address field exceeding maximum length shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongAddress = 'A'.repeat(501); // Exceeds typical address field limit
    await page.locator('#input_34_278879').fill('INV123456789');
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').fill('john.smith@example.com');
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').fill(tooLongAddress);
    
    await page.locator('#searchsubmit').click();
    
    await expect(page.getByText('too long'), 'Address exceeding maximum length should show validation error').toBeVisible();
  });

  test('boundary — URL-like input in email field shows format validation', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.locator('#input_34_278879').fill('INV123456789');
    await page.locator('#input_34_8_3').fill('John');
    await page.locator('#input_34_8_6').fill('Smith');
    await page.locator('#input_34_3').fill('https://www.example.com');
    await page.locator('#input_34_4').fill('+1-555-123-4567');
    await page.locator('#input_34_5').fill('123 Main Street, New York, NY 10001');
    
    await page.locator('#searchsubmit').click();
    
    await expect(page.getByText('valid email'), 'URL input in email field should show email format validation error').toBeVisible();
  });
});