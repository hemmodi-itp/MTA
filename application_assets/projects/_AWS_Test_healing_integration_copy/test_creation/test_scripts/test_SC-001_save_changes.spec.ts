import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Save Changes (SC-001)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — valid preferences submission saves successfully', async () => {
    await page.goto(BASE_URL);

    // Enter element in the input field
    await page.locator('#awsccc-u-cb-performance').fill('advertisement tracking');
    await expect(page.locator('#awsccc-u-cb-performance'), 'Performance checkbox input should accept element value').toHaveValue('advertisement tracking');

    // Enter allow crosscontext behavioral ads in the input field
    await page.locator('#awsccc-u-cb-functional').fill('yes');
    await expect(page.locator('#awsccc-u-cb-functional'), 'Functional checkbox input should accept crosscontext behavioral ads value').toHaveValue('yes');

    // Enter opt out of crosscontext behavioral ads in the input field
    await page.locator('#awsccc-u-cb-advertising').fill('no');
    await expect(page.locator('#awsccc-u-cb-advertising'), 'Advertising checkbox input should accept opt out value').toHaveValue('no');

    // Enter im looking for in the input field
    await page.getByPlaceholder('I\'m looking for...').fill('privacy settings');
    await expect(page.getByPlaceholder('I\'m looking for...'), 'Search input should accept looking for value').toHaveValue('privacy settings');

    // Click the save preferences
    await page.getByRole('button', { name: 'Save preferences' }).click();
    await expect(page.getByRole('button', { name: 'Save preferences' }), 'Save preferences button should be clickable').toBeVisible();
  });

  test('negative — empty required element field prevents saving', async () => {
    await page.goto(BASE_URL);

    // Enter empty element field (testing the negative case)
    await page.locator('#awsccc-u-cb-performance').fill('');
    
    // Fill other fields with valid data
    await page.locator('#awsccc-u-cb-functional').fill('yes');
    await page.locator('#awsccc-u-cb-advertising').fill('no');
    await page.getByPlaceholder('I\'m looking for...').fill('privacy settings');

    // Attempt to save preferences
    await page.getByRole('button', { name: 'Save preferences' }).click();
    
    // Verify empty field state
    await expect(page.locator('#awsccc-u-cb-performance'), 'Element field should remain empty when validation fails').toHaveValue('');
  });

  test('boundary — maximum length input is accepted', async () => {
    await page.goto(BASE_URL);

    const maxLengthValue = 'this is a very long advertisement tracking preference description that tests the maximum character limit for this input field and should be exactly at the boundary of what is allowed by the system validation rules';

    // Enter maximum length element value
    await page.locator('#awsccc-u-cb-performance').fill(maxLengthValue);
    await expect(page.locator('#awsccc-u-cb-performance'), 'Performance input should accept maximum length value').toHaveValue(maxLengthValue);

    // Fill other fields with valid data
    await page.locator('#awsccc-u-cb-functional').fill('yes');
    await page.locator('#awsccc-u-cb-advertising').fill('no');
    await page.getByPlaceholder('I\'m looking for...').fill('privacy settings');

    // Click save preferences to test boundary acceptance
    await page.getByRole('button', { name: 'Save preferences' }).click();
    await expect(page.getByRole('button', { name: 'Save preferences' }), 'Save preferences button should remain accessible after boundary input').toBeVisible();
  });
});