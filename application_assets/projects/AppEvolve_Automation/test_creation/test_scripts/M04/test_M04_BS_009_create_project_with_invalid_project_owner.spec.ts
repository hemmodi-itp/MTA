import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/projects';

test.describe.configure({ mode: 'serial' });

test.describe('Create Project with Invalid Project Owner (M04_BS_009)', () => {
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

  test('positive — valid project creation with valid owner', async () => {
    await page.goto(BASE_URL);
    
    // Navigate to project creation (assuming there's a button or link to open the Add Project popup)
    // Since no specific locators are provided, we'll use common patterns
    await page.getByText('Add Project').click();
    
    // Fill in project details with valid data
    await page.locator('#projects-create-name').fill('TestProject');
    await page.locator('#projects-create-description').fill('Test Description');
    await page.locator('#projects-create-owner').fill('john.doe@company.com');
    
    // Submit the form
    await page.getByRole('button', { name: 'Create Project' }).click();
    
    // Verify successful project creation
    await expect(page.getByText('Project created successfully'), 'Success message should appear after valid project creation').toBeVisible();
  });

  test('negative — invalid project owner validation error', async () => {
    const negativeIterations = [
      {
        projectName: 'TestProject',
        projectDescription: 'Test Description',
        projectOwner: 'InvalidUser@nonexistent.com',
        expectedError: 'Project owner does not exist in the system'
      },
      {
        projectName: 'TestProject',
        projectDescription: 'Test Description',
        projectOwner: 'invalid-email-format',
        expectedError: 'Invalid email format for project owner'
      }
    ];

    for (const iteration of negativeIterations) {
      await page.goto(BASE_URL);
      
      // Open Add Project popup
      await page.getByText('Add Project').click();
      
      // Fill in project details with invalid owner data
      await page.locator('#projects-create-name').fill(iteration.projectName);
      await page.locator('#projects-create-description').fill(iteration.projectDescription);
      await page.locator('#projects-create-owner').fill(iteration.projectOwner);
      
      // Attempt to submit the form
      await page.getByRole('button', { name: 'Create Project' }).click();
      
      // Verify validation error appears
      await expect(page.getByText(iteration.expectedError), `Validation error "${iteration.expectedError}" should appear for invalid project owner`).toBeVisible();
    }
  });

  test('boundary — project owner email at maximum length limit', async () => {
    await page.goto(BASE_URL);
    
    // Open Add Project popup
    await page.getByText('Add Project').click();
    
    // Fill in project details with maximum length email
    await page.locator('#projects-create-name').fill('TestProject');
    await page.locator('#projects-create-description').fill('Test Description');
    await page.locator('#projects-create-owner').fill('verylongusernamethatapproachesthemaximumlengthallowedforemailaddressesinthesystemwhichshouldbehandledproperlybythesystemvalidationandnotcauseanyunexpectedbehaviororerrorsintheapplicationflowduringprojectcreation@company.com');
    
    // Attempt to submit the form
    await page.getByRole('button', { name: 'Create Project' }).click();
    
    // Verify length validation error appears
    await expect(page.getByText('Project owner email must be 255 characters or less'), 'Length validation error should appear for email exceeding maximum length').toBeVisible();
  });
});