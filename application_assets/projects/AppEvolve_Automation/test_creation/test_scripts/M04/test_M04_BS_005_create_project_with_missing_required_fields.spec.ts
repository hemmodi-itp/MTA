import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/projects';

test.describe.configure({ mode: 'serial' });

test.describe('Create Project with Missing Required Fields (M04_BS_005)', () => {
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

  test('positive — valid project creation with all required fields', async () => {
    await page.goto(BASE_URL);
    
    // Open the Add Project popup
    await page.getByRole('button', { name: 'Add Project' }).click();
    
    // Fill all required fields with valid data
    await page.locator('#projects-create-name').fill('Customer Portal Redesign');
    await page.locator('#projects-create-description').fill('Modernize the customer-facing portal with improved UX, mobile responsiveness, and enhanced security features to increase user engagement and satisfaction.');
    await page.locator('#projects-create-owner').fill('Sarah Johnson');
    
    // Submit the form
    await page.getByRole('button', { name: 'Create Project' }).click();
    
    // Verify successful project creation (assuming redirect or success message)
    await expect(page, 'Page should navigate after successful project creation').toHaveURL(/.*projects.*/);
  });

  test('negative — missing required fields show validation errors', async () => {
    const iterations = [
      {
        fields: [
          { name: 'fill_project_name', value: '' },
          { name: 'fill_project_description', value: 'Modernize the customer-facing portal with improved UX, mobile responsiveness, and enhanced security features to increase user engagement and satisfaction.' },
          { name: 'select_project_owner', value: 'Sarah Johnson' }
        ],
        expected_error: 'Project Name is required'
      },
      {
        fields: [
          { name: 'fill_project_name', value: 'Customer Portal Redesign' },
          { name: 'fill_project_description', value: '' },
          { name: 'select_project_owner', value: 'Sarah Johnson' }
        ],
        expected_error: 'Project Description is required'
      },
      {
        fields: [
          { name: 'fill_project_name', value: 'Customer Portal Redesign' },
          { name: 'fill_project_description', value: 'Modernize the customer-facing portal with improved UX, mobile responsiveness, and enhanced security features to increase user engagement and satisfaction.' },
          { name: 'select_project_owner', value: '' }
        ],
        expected_error: 'Project Owner is required'
      }
    ];

    for (const iteration of iterations) {
      await page.goto(BASE_URL);
      
      // Open the Add Project popup
      await page.getByRole('button', { name: 'Add Project' }).click();
      
      // Fill fields based on iteration data
      const projectNameField = iteration.fields.find(f => f.name === 'fill_project_name');
      const projectDescField = iteration.fields.find(f => f.name === 'fill_project_description');
      const projectOwnerField = iteration.fields.find(f => f.name === 'select_project_owner');
      
      await page.locator('#projects-create-name').fill(projectNameField?.value || '');
      await page.locator('#projects-create-description').fill(projectDescField?.value || '');

      if (projectOwnerField?.value) {
        await page.locator('#projects-create-owner').fill(projectOwnerField.value);
      }
      
      // Attempt to submit the form
      await page.getByRole('button', { name: 'Create Project' }).click();
      
      // Verify validation error appears
      await expect(page.getByText(iteration.expected_error), `Validation error "${iteration.expected_error}" should be displayed`).toBeVisible();
    }
  });

  test('boundary — project name exceeds maximum length limit', async () => {
    await page.goto(BASE_URL);
    
    // Open the Add Project popup
    await page.getByRole('button', { name: 'Add Project' }).click();
    
    // Fill with boundary test data
    const longProjectName = 'This is a very long project name that approaches the maximum character limit for project names in the system to test boundary conditions and ensure proper validation is working as expected for edge cases in data input';
    
    await page.locator('#projects-create-name').fill(longProjectName);
    await page.locator('#projects-create-description').fill('Modernize the customer-facing portal with improved UX, mobile responsiveness, and enhanced security features to increase user engagement and satisfaction.');
    await page.locator('#projects-create-owner').fill('Sarah Johnson');
    
    // Attempt to submit the form
    await page.getByRole('button', { name: 'Create Project' }).click();
    
    // Verify validation error for length limit
    await expect(page.getByText('Project Name must be 255 characters or less'), 'Length validation error should be displayed for project name exceeding limit').toBeVisible();
  });
});