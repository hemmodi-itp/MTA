import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/projects';

test.describe.configure({ mode: 'serial' });

test.describe('Create Project with Maximum Character Limits (M04_BS_010)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await page.goto("https://pt-dev.appevolve.intuitive.ai/");
    await page.locator("button:has-text('SSO Login')").click();
    await page.waitForTimeout(4000);
    await page.locator("#username").fill(process.env.APPEVOLVE_AUTOMATION_DEV_USERNAME ?? "");
    await page.locator("#password").fill(process.env.APPEVOLVE_AUTOMATION_DEV_PASSWORD ?? "");
    await page.locator("#kc-login").click();
    await page.waitForTimeout(2000);
    await page.locator("button.joyride__hurray-btn").click();
    await page.waitForTimeout(1000);
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — create project with valid field lengths within limits', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to add project functionality (assuming button/link exists)
    await page.click('text=Add Project', { timeout: 10000 });
    
    // Fill project name with valid length
    await page.fill('#projects-create-name', 'Customer Portal Redesign');
    
    // Fill project description with valid length
    await page.fill('#projects-create-description', 'A comprehensive redesign of our customer portal to improve user experience, streamline navigation, and integrate new self-service features for account management and support requests.');
    
    // Fill project owner
    await page.fill('#projects-create-owner', 'Sarah Johnson');
    
    // Submit the form
    await page.click('button:has-text("Create Project")');
    
    // Verify successful creation (check URL or success message if available)
    await expect(page, 'Should navigate away from create form after successful project creation').not.toHaveURL(/add|create/);
  });

  test('negative — required fields left empty show validation errors', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to add project functionality
    await page.click('text=Add Project', { timeout: 10000 });
    
    // Leave all fields empty and attempt to create project
    await page.fill('#projects-create-name', '');
    await page.fill('#projects-create-description', '');
    await page.fill('#projects-create-owner', '');
    
    // Submit the form
    await page.click('button:has-text("Create Project")');
    
    // Verify validation errors appear (checking for error text or staying on same page)
    await expect(page, 'Should remain on create project page when validation fails').toHaveURL(/add|create/);
  });

  test('boundary — fields exceeding maximum character limits show validation errors', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to add project functionality
    await page.click('text=Add Project', { timeout: 10000 });
    
    // Fill fields with values exceeding maximum character limits
    await page.fill('#projects-create-name', 'This is an extremely long project name that exceeds the maximum allowed character limit for project names in the system and should trigger a validation error when the user attempts to create the project with this overly verbose title that goes on and on without end');
    
    await page.fill('#projects-create-description', 'This is an extremely long project description that exceeds the maximum allowed character limit for project descriptions in the system. It contains way too much information and details that go beyond what should reasonably be allowed in a single description field, continuing with more unnecessary text to push it well over any reasonable character limit that a system would impose on such fields to ensure proper data management and user interface constraints are maintained throughout the application lifecycle and beyond what any reasonable user would actually need to describe their project in a concise and meaningful way.');
    
    await page.fill('#projects-create-owner', 'Sarah Johnson');
    
    // Submit the form
    await page.click('button:has-text("Create Project")');
    
    // Verify validation errors prevent project creation
    await expect(page, 'Should remain on create project page when character limits are exceeded').toHaveURL(/add|create/);
  });
});