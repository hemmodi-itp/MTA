import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://alterdomus.com/services/investor-management/';

test.describe('Investor Communication and Announcement Distribution (BS-008)', () => {

  test('positive — complete announcement creation and distribution workflow succeeds', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Navigate to communications section
    await page.getByRole('link', { name: 'Communications' }).click();
    await expect(page.getByText('Communication Management'), 'Communication management page should be displayed').toBeVisible();
    
    // Create new announcement
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    await expect(page.getByText('New Announcement'), 'New announcement form should be displayed').toBeVisible();
    
    // Fill announcement details
    await page.getByPlaceholder('Announcement Title').fill('Q3 2024 Financial Results');
    await page.getByPlaceholder('Message Content').fill('We are pleased to announce our Q3 2024 financial results showing strong performance across all sectors.');
    
    // Select target investor groups
    await page.getByRole('button', { name: 'Select Investor Groups' }).click();
    await page.getByRole('checkbox', { name: 'All Investors' }).check();
    await expect(page.getByRole('checkbox', { name: 'All Investors' }), 'All investors group should be selected').toBeChecked();
    
    // Review content
    await page.getByRole('button', { name: 'Preview' }).click();
    await expect(page.getByText('Q3 2024 Financial Results'), 'Announcement title should appear in preview').toBeVisible();
    await expect(page.getByText('We are pleased to announce'), 'Announcement content should appear in preview').toBeVisible();
    
    // Approve and distribute
    await page.getByRole('button', { name: 'Approve & Send' }).click();
    await page.getByRole('button', { name: 'Confirm Distribution' }).click();
    
    // Verify distribution success
    await expect(page.getByText('Communication sent successfully'), 'Success message should be displayed after distribution').toBeVisible();
    
    // Check tracking dashboard
    await page.getByRole('link', { name: 'Track Communications' }).click();
    await expect(page.getByText('Q3 2024 Financial Results'), 'Sent announcement should appear in tracking dashboard').toBeVisible();
    await expect(page.getByText('Delivered'), 'Communication status should show as delivered').toBeVisible();
    
    // Verify audit log entry
    await page.getByRole('link', { name: 'Audit Log' }).click();
    await expect(page.getByText('Communication distributed'), 'Audit log should contain distribution entry').toBeVisible();
  });

  test('negative — empty announcement title shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    
    // Leave title empty and fill content
    await page.getByPlaceholder('Message Content').fill('Test content without title');
    
    // Attempt to proceed
    await page.getByRole('button', { name: 'Preview' }).click();
    
    await expect(page.getByText('Title is required'), 'Validation error should be shown for empty title').toBeVisible();
    await expect(page.getByText('New Announcement'), 'Should remain on announcement creation form').toBeVisible();
  });

  test('negative — special characters in announcement title shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    
    // Fill with special characters
    await page.getByPlaceholder('Announcement Title').fill('<script>alert("test")</script>');
    await page.getByPlaceholder('Message Content').fill('Valid message content');
    
    await page.getByRole('button', { name: 'Preview' }).click();
    
    await expect(page.getByText('Invalid characters in title'), 'Validation error should be shown for special characters').toBeVisible();
  });

  test('negative — SQL injection attempt in message content is blocked', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    
    await page.getByPlaceholder('Announcement Title').fill('Valid Title');
    await page.getByPlaceholder('Message Content').fill("'; DROP TABLE investors; --");
    
    await page.getByRole('button', { name: 'Preview' }).click();
    
    await expect(page.getByText('Invalid content detected'), 'Security validation error should be displayed').toBeVisible();
  });

  test('negative — wrong email format in notification settings shows error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Settings' }).click();
    
    await page.getByPlaceholder('Reply-to Email').fill('invalid-email-format');
    await page.getByRole('button', { name: 'Save Settings' }).click();
    
    await expect(page.getByText('Please enter a valid email address'), 'Email format validation error should be displayed').toBeVisible();
  });

  test('boundary — announcement title at maximum length (255 chars) is accepted', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const maxLengthTitle = 'A'.repeat(255);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    
    await page.getByPlaceholder('Announcement Title').fill(maxLengthTitle);
    await page.getByPlaceholder('Message Content').fill('Valid message content');
    
    await page.getByRole('button', { name: 'Preview' }).click();
    
    await expect(page.getByText(maxLengthTitle.substring(0, 50)), 'Title at maximum length should be accepted in preview').toBeVisible();
  });

  test('boundary — announcement title exceeding maximum length shows validation error', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const tooLongTitle = 'A'.repeat(256);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    
    await page.getByPlaceholder('Announcement Title').fill(tooLongTitle);
    await page.getByPlaceholder('Message Content').fill('Valid message content');
    
    await page.getByRole('button', { name: 'Preview' }).click();
    
    await expect(page.getByText('Title exceeds maximum length of 255 characters'), 'Length validation error should be displayed').toBeVisible();
  });

  test('boundary — URL input in message content is properly sanitized', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.getByRole('link', { name: 'Communications' }).click();
    await page.getByRole('button', { name: 'Create Announcement' }).click();
    
    await page.getByPlaceholder('Announcement Title').fill('URL Test Announcement');
    await page.getByPlaceholder('Message Content').fill('Please visit our website at https://example.com/investor-portal for more information.');
    
    await page.getByRole('button', { name: 'Preview' }).click();
    
    await expect(page.getByText('Please visit our website at'), 'Message with URL should be displayed in preview').toBeVisible();
    await expect(page.getByRole('link', { name: 'https://example.com/investor-portal' }), 'URL should be properly formatted as clickable link').toBeVisible();
  });

});