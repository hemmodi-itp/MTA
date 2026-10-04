import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/projects';

test.describe.configure({ mode: 'serial' });

test.describe('Create New Project Successfully (M04_BS_003)', () => {
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

  test('positive — create project with valid information succeeds', async () => {
    await page.goto(BASE_URL);
    
    // Click on Add Project
    await page.getByText('Add Project').click();
    
    // Enter project name
    await page.locator('#projects-create-name').fill('E-Commerce Platform Redesign');

    // Enter project description
    await page.locator('#projects-create-description').fill('Complete redesign of the customer-facing e-commerce platform to improve user experience and increase conversion rates. Includes mobile responsiveness, payment gateway integration, and performance optimization.');

    // Enter project owner
    await page.locator('#projects-create-owner').fill('Sarah Johnson');
    
    // Click Create Project button
    await page.getByRole('button', { name: 'Create Project' }).click();
    
    // Verify project creation success
    await expect(page.getByText('E-Commerce Platform Redesign'), 'Created project should be visible in the project list').toBeVisible();
    await expect(page.getByText('Sarah Johnson'), 'Project owner should be displayed').toBeVisible();
  });

  test('negative — missing required fields show validation errors', async () => {
    const iterations = [
      {
        fields: {
          project_name: '',
          project_description: 'Complete redesign of the customer-facing e-commerce platform to improve user experience and increase conversion rates. Includes mobile responsiveness, payment gateway integration, and performance optimization.',
          project_owner: 'Sarah Johnson'
        },
        expected_error: 'Project name is required'
      },
      {
        fields: {
          project_name: 'E-Commerce Platform Redesign',
          project_description: 'Complete redesign of the customer-facing e-commerce platform to improve user experience and increase conversion rates. Includes mobile responsiveness, payment gateway integration, and performance optimization.',
          project_owner: ''
        },
        expected_error: 'Project owner is required'
      }
    ];

    for (const iteration of iterations) {
      await page.goto(BASE_URL);
      
      // Click on Add Project
      await page.getByText('Add Project').click();
      
      // Fill form with test data
      await page.locator('#projects-create-name').fill(iteration.fields.project_name);
      await page.locator('#projects-create-description').fill(iteration.fields.project_description);
      await page.locator('#projects-create-owner').fill(iteration.fields.project_owner);
      
      // Click Create Project button
      await page.getByRole('button', { name: 'Create Project' }).click();
      
      // Verify validation error appears
      await expect(page.getByText(iteration.expected_error), `Validation error "${iteration.expected_error}" should be displayed`).toBeVisible();
    }
  });

  test('boundary — project name exceeds maximum length shows validation error', async () => {
    await page.goto(BASE_URL);
    
    // Click on Add Project
    await page.getByText('Add Project').click();
    
    // Fill form with boundary test data
    await page.locator('#projects-create-name').fill('This is an extremely long project name that exceeds the normal character limit for project names and should trigger a validation error because it contains way too many characters and goes beyond what would be considered a reasonable length');
    await page.locator('#projects-create-description').fill('Complete redesign of the customer-facing e-commerce platform to improve user experience and increase conversion rates. Includes mobile responsiveness, payment gateway integration, and performance optimization.');
    await page.locator('#projects-create-owner').fill('Sarah Johnson');
    
    // Click Create Project button
    await page.getByRole('button', { name: 'Create Project' }).click();
    
    // Verify validation error appears
    await expect(page.getByText('Project name must be 255 characters or less'), 'Length validation error should be displayed for project name').toBeVisible();
  });
});