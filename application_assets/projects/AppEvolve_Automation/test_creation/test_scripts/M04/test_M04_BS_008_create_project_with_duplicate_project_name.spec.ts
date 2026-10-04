import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/projects';

test.describe.configure({ mode: 'serial' });

test.describe('Create Project with Duplicate Project Name (M04_BS_008)', () => {
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

  test('positive — create project with duplicate name triggers validation', async () => {
    await page.goto(BASE_URL);
    
    // First, ensure the existing project is present by creating it
    // This test verifies the system properly handles duplicate project names
    // so we need to simulate the scenario where ExistingProject already exists
    
    // Click on Add Project
    await page.getByText('Add Project').click();
    
    // Fill in the project form with duplicate name
    await page.locator('#projects-create-name').fill('ExistingProject');
    await page.locator('#projects-create-description').fill('Test Description');
    await page.locator('#projects-create-owner').fill('John Doe');

    // Click create project button
    await page.getByRole('button', { name: 'Create Project' }).click();

    // Verify that appropriate validation message is displayed
    await expect(page.getByText('A project with this name already exists'), 'Duplicate project name validation message should be displayed').toBeVisible();

    // Verify the project was not created (we should still be on the creation form)
    await expect(page.locator('#projects-create-name'), 'Project name field should still be visible indicating project was not created').toBeVisible();
  });

  test('negative — duplicate project name validation with error message', async () => {
    await page.goto(BASE_URL);
    
    const negativeData = [
      {
        projectName: 'ExistingProject',
        description: 'Test Description',
        owner: 'John Doe',
        expectedError: 'A project with this name already exists. Please choose a different name.'
      }
    ];

    for (const data of negativeData) {
      await page.getByText('Add Project').click();
      
      await page.locator('#projects-create-name').fill(data.projectName);
      await page.locator('#projects-create-description').fill(data.description);
      await page.locator('#projects-create-owner').fill(data.owner);
      
      await page.getByRole('button', { name: 'Create Project' }).click();
      
      // Verify the expected error message is displayed
      await expect(page.getByText(data.expectedError), `Expected error message "${data.expectedError}" should be displayed`).toBeVisible();
      
      // Navigate back for next iteration if needed
      await page.goto(BASE_URL);
    }
  });

  test('boundary — project name at maximum length validation', async () => {
    await page.goto(BASE_URL);
    
    const boundaryData = [
      {
        projectName: 'ExistingProjectNameThatIsExactlyAtTheMaximumAllowedLengthForProjectNamesInTheSystemWhichShouldBeValidatedProperlyByTheApplicationToEnsureDataIntegrityAndUserExperienceRemainsOptimalThroughoutTheEntireProjectCreationWorkflowProcess',
        description: 'Test Description',
        owner: 'John Doe',
        expectedError: 'Project name must be 255 characters or less'
      }
    ];

    for (const data of boundaryData) {
      await page.getByText('Add Project').click();
      
      await page.locator('#projects-create-name').fill(data.projectName);
      await page.locator('#projects-create-description').fill(data.description);
      await page.locator('#projects-create-owner').fill(data.owner);

      await page.getByRole('button', { name: 'Create Project' }).click();

      // Verify the expected error message for maximum length is displayed
      await expect(page.getByText(data.expectedError), `Expected length validation error "${data.expectedError}" should be displayed`).toBeVisible();
      
      // Navigate back for next iteration if needed
      await page.goto(BASE_URL);
    }
  });
});