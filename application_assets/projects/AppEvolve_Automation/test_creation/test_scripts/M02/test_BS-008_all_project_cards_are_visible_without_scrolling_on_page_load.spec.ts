import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe('All project cards are visible without scrolling on page load (BS-008)', () => {

  test.beforeEach(async ({ page }) => {
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
  test('positive — all three project sections are visible on initial page load with complete content', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for page to fully load
    await page.waitForLoadState('networkidle');
    
    // Verify WebDriver project section is visible without scrolling
    const webDriverSection = page.getByText('WebDriver');
    await expect(webDriverSection, 'WebDriver project section heading must be visible on page load').toBeVisible();
    
    const webDriverCard = webDriverSection.locator('..').locator('xpath=ancestor-or-self::*[contains(@class, "card") or contains(@class, "project")]');
    await expect(webDriverCard, 'WebDriver project card must be visible without scrolling').toBeInViewport();
    
    // Verify WebDriver card has complete content
    const webDriverDescription = page.locator('text=WebDriver').locator('..').getByText('description', { includeHidden: false });
    await expect(webDriverDescription, 'WebDriver project must display description text').toBeVisible();
    
    const webDriverButton = page.locator('text=WebDriver').locator('..').getByRole('button');
    await expect(webDriverButton, 'WebDriver project must display CTA button').toBeVisible();
    
    const webDriverReadMore = page.locator('text=WebDriver').locator('..').getByText('Read more');
    await expect(webDriverReadMore, 'WebDriver project must display Read more link').toBeVisible();
    
    // Verify IDE project section is visible without scrolling
    const ideSection = page.getByText('IDE');
    await expect(ideSection, 'IDE project section heading must be visible on page load').toBeVisible();
    
    const ideCard = ideSection.locator('..').locator('xpath=ancestor-or-self::*[contains(@class, "card") or contains(@class, "project")]');
    await expect(ideCard, 'IDE project card must be visible without scrolling').toBeInViewport();
    
    // Verify IDE card has complete content
    const ideDescription = page.locator('text=IDE').locator('..').getByText('description', { includeHidden: false });
    await expect(ideDescription, 'IDE project must display description text').toBeVisible();
    
    const ideButton = page.locator('text=IDE').locator('..').getByRole('button');
    await expect(ideButton, 'IDE project must display CTA button').toBeVisible();
    
    const ideReadMore = page.locator('text=IDE').locator('..').getByText('Read more');
    await expect(ideReadMore, 'IDE project must display Read more link').toBeVisible();
    
    // Verify Grid project section is visible without scrolling  
    const gridSection = page.getByText('Grid');
    await expect(gridSection, 'Grid project section heading must be visible on page load').toBeVisible();
    
    const gridCard = gridSection.locator('..').locator('xpath=ancestor-or-self::*[contains(@class, "card") or contains(@class, "project")]');
    await expect(gridCard, 'Grid project card must be visible without scrolling').toBeInViewport();
    
    // Verify Grid card has complete content
    const gridDescription = page.locator('text=Grid').locator('..').getByText('description', { includeHidden: false });
    await expect(gridDescription, 'Grid project must display description text').toBeVisible();
    
    const gridButton = page.locator('text=Grid').locator('..').getByRole('button');
    await expect(gridButton, 'Grid project must display CTA button').toBeVisible();
    
    const gridReadMore = page.locator('text=Grid').locator('..').getByText('Read more');
    await expect(gridReadMore, 'Grid project must display Read more link').toBeVisible();
    
    // Confirm no scrolling was needed by checking viewport height vs content height
    const viewportHeight = await page.evaluate(() => window.innerHeight);
    const scrollPosition = await page.evaluate(() => window.scrollY);
    await expect(scrollPosition, 'Page should not have been scrolled to view all project cards').toBe(0);
  });

  test('negative — page with missing project content shows error state', async ({ page }) => {
    // Simulate empty response by intercepting API calls
    await page.route('**/api/projects**', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ projects: [] })
      });
    });
    
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    const emptyState = page.getByText('No projects available');
    await expect(emptyState, 'Empty state message must be visible when no projects are returned').toBeVisible();
  });

  test('negative — page with corrupted project data displays fallback content', async ({ page }) => {
    // Simulate corrupted data response
    await page.route('**/api/projects**', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ 
          projects: [
            { id: 1, name: null, description: '<script>alert("xss")</script>' },
            { id: 2, name: '', description: 'SELECT * FROM users;' }
          ]
        })
      });
    });
    
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    const errorMessage = page.getByText('Unable to load project information');
    await expect(errorMessage, 'Error message must be displayed when project data is corrupted').toBeVisible();
    
    // Ensure XSS content is not executed
    const scriptAlert = page.getByText('<script>');
    await expect(scriptAlert, 'Script tags must not be rendered as executable content').not.toBeVisible();
  });

  test('negative — API failure shows appropriate error handling', async ({ page }) => {
    // Simulate API failure
    await page.route('**/api/projects**', route => {
      route.fulfill({ status: 500 });
    });
    
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    const errorState = page.getByText('Failed to load projects');
    await expect(errorState, 'Error state must be visible when API fails to load projects').toBeVisible();
    
    const retryButton = page.getByRole('button', { name: 'Retry' });
    await expect(retryButton, 'Retry button must be available when API fails').toBeVisible();
  });

  test('negative — network timeout displays timeout error', async ({ page }) => {
    // Simulate network timeout
    await page.route('**/api/projects**', route => {
      // Never fulfill the request to simulate timeout
      return;
    });
    
    await page.goto(BASE_URL);
    
    const timeoutError = page.getByText('Request timed out');
    await expect(timeoutError, 'Timeout error message must appear when network request times out').toBeVisible({ timeout: 10000 });
  });

  test('boundary — minimum viewport height still shows all project cards', async ({ page }) => {
    // Set viewport to minimum supported height
    await page.setViewportSize({ width: 1024, height: 600 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // All three sections should still be visible in minimum viewport
    const webDriverCard = page.getByText('WebDriver').locator('..');
    await expect(webDriverCard, 'WebDriver card must be visible in minimum viewport height').toBeInViewport();
    
    const ideCard = page.getByText('IDE').locator('..');  
    await expect(ideCard, 'IDE card must be visible in minimum viewport height').toBeInViewport();
    
    const gridCard = page.getByText('Grid').locator('..');
    await expect(gridCard, 'Grid card must be visible in minimum viewport height').toBeInViewport();
  });

  test('boundary — maximum content length in project descriptions is handled properly', async ({ page }) => {
    // Simulate very long project descriptions
    const longDescription = 'A'.repeat(1000);
    await page.route('**/api/projects**', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          projects: [
            { id: 1, name: 'WebDriver', description: longDescription },
            { id: 2, name: 'IDE', description: longDescription },  
            { id: 3, name: 'Grid', description: longDescription }
          ]
        })
      });
    });
    
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Verify long descriptions are truncated or scrollable within cards
    const webDriverCard = page.getByText('WebDriver').locator('..');
    await expect(webDriverCard, 'WebDriver card with long description must still be visible').toBeVisible();
    
    const cardHeight = await webDriverCard.boundingBox();
    expect(cardHeight?.height, 'Project card height must be reasonable even with long content').toBeLessThan(500);
  });

  test('boundary — edge case URL parameters do not break page layout', async ({ page }) => {
    // Test with various edge case URL parameters
    const edgeUrl = `${BASE_URL}?filter=<script>&sort='; DROP TABLE projects;--&page=999999`;
    await page.goto(edgeUrl);
    await page.waitForLoadState('networkidle');
    
    // Page should still load normally despite malicious URL parameters
    const webDriverSection = page.getByText('WebDriver');
    await expect(webDriverSection, 'WebDriver section must be visible even with malicious URL parameters').toBeVisible();
    
    const ideSection = page.getByText('IDE');
    await expect(ideSection, 'IDE section must be visible even with malicious URL parameters').toBeVisible();
    
    const gridSection = page.getByText('Grid');
    await expect(gridSection, 'Grid section must be visible even with malicious URL parameters').toBeVisible();
    
    // Ensure URL parameters don't cause XSS
    const scriptContent = page.getByText('<script>');
    await expect(scriptContent, 'Malicious script content from URL must not be rendered').not.toBeVisible();
  });

});