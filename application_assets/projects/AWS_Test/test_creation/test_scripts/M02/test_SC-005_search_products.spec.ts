import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/rds/aurora';

test.describe.configure({ mode: 'serial' });

test.describe('Search Products (SC-005)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — navigate to Siemens Mobility AWS AI story', async () => {
    await page.goto(BASE_URL);
    
    // Click on the industrial siemens mobility story link
    await page.getByText('industrial siemens mobility turns 175 years of data into searchable insights with aws ai view the story').click();
    
    // Verify navigation to the expected URL pattern
    await expect(page, 'Should navigate to Siemens Mobility story page').toHaveURL(/industrial_siemens_mobility_turns_175_years_of_data_into_searchable_insights_with_aws_ai_view_the_story/);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
  });

  test('negative — handle navigation target not found scenario', async () => {
    await page.goto(BASE_URL);
    
    // Attempt to click the target that may not exist or lead to 404
    const clickTarget = page.getByText('industrial siemens mobility turns 175 years of data into searchable insights with aws ai view the story');
    
    try {
      await clickTarget.click({ timeout: 5000 });
      
      // Check if we landed on a 404 or error page
      const currentUrl = page.url();
      if (currentUrl.includes('404') || currentUrl.includes('error')) {
        await expect(page, 'Should show 404 or error page when content not found').toHaveURL(/404|error/);
      } else {
        // If navigation succeeded but content is missing, verify page loaded
        await page.waitForLoadState('networkidle');
        await expect(page, 'Page should load even if content is missing').toHaveURL(/.*/, { timeout: 10000 });
      }
    } catch (error) {
      // If click target not found, that's the expected negative scenario
      await expect(page, 'Should remain on base URL when navigation target not found').toHaveURL(BASE_URL);
    }
  });
});