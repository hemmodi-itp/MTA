import { test, expect, Page } from '@playwright/test';
const BASE_URL = process.env.BASE_URL || 'https://aws.amazon.com/pricing/';

test.describe.configure({ mode: 'serial' });

test.describe('Browse pricing information for multiple AWS products (M03_BS_010)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test('positive — successfully browse pricing for multiple AWS products', async () => {
    await page.goto(BASE_URL);
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Verify we're on the AWS pricing page
    await expect(page, 'Should be on AWS pricing page').toHaveURL(/aws\.amazon\.com\/pricing/);
    
    // Navigate through the pricing page to find product information
    // Since no specific locators are provided, we'll scroll and search for pricing content
    await page.evaluate(() => window.scrollTo(0, 0));
    
    // Look for common AWS service pricing patterns by searching the page content
    const pageContent = await page.content();
    
    // Track services found
    let servicesFound = 0;
    const targetServices = ['firewall', 'ec2', 'glue', 'iot'];
    
    // Check if we can find references to target services in page content
    for (const service of targetServices) {
      if (pageContent.toLowerCase().includes(service)) {
        servicesFound++;
      }
    }
    
    // Scroll through the page to discover more services
    await page.evaluate(() => {
      window.scrollBy(0, 500);
    });
    await page.waitForTimeout(1000);
    
    await page.evaluate(() => {
      window.scrollBy(0, 500);
    });
    await page.waitForTimeout(1000);
    
    // Look for additional AWS services commonly found on pricing pages
    const additionalServices = ['lambda', 's3', 'rds', 'dynamodb', 'cloudfront', 'vpc'];
    const finalContent = await page.content();
    
    for (const service of additionalServices) {
      if (finalContent.toLowerCase().includes(service)) {
        servicesFound++;
      }
    }
    
    // Verify we found pricing information for multiple services
    await expect(servicesFound, 'Should find pricing information for at least 6 AWS services').toBeGreaterThanOrEqual(6);
    
    // Verify page contains pricing-related content
    await expect(page.locator('body'), 'Page should contain pricing information').toContainText(/pricing|price|cost|\$/i);
  });

  test('negative — handle missing or unavailable pricing sections', async () => {
    await page.goto(BASE_URL + 'invalid-service');
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Should either redirect to valid pricing page or show error
    const currentUrl = page.url();
    const pageContent = await page.content();
    
    if (currentUrl.includes('invalid-service')) {
      // If we stayed on invalid URL, expect error content
      await expect(page.locator('body'), 'Should show error message for invalid service').toContainText(/not found|error|unavailable/i);
    } else {
      // If redirected to valid pricing page, verify we're back on pricing
      await expect(page, 'Should redirect to valid pricing page').toHaveURL(/aws\.amazon\.com\/pricing/);
    }
  });

  test('boundary — verify minimum product count threshold', async () => {
    await page.goto(BASE_URL);
    
    await page.waitForLoadState('networkidle');
    
    // Scroll through entire page to count all available services
    let previousHeight = 0;
    let currentHeight = await page.evaluate(() => document.body.scrollHeight);
    
    while (previousHeight !== currentHeight) {
      previousHeight = currentHeight;
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(1000);
      currentHeight = await page.evaluate(() => document.body.scrollHeight);
    }
    
    const fullPageContent = await page.content();
    
    // Count AWS services mentioned in content
    const awsServices = [
      'ec2', 'lambda', 's3', 'rds', 'dynamodb', 'cloudfront', 'vpc', 'iam',
      'glue', 'iot', 'waf', 'shield', 'cloudwatch', 'sns', 'sqs', 'api gateway'
    ];
    
    let serviceCount = 0;
    for (const service of awsServices) {
      if (fullPageContent.toLowerCase().includes(service)) {
        serviceCount++;
      }
    }
    
    // Verify we meet minimum threshold of 3 services (boundary case)
    await expect(serviceCount, 'Should find at least 3 AWS services on pricing page').toBeGreaterThanOrEqual(3);
    
    // Verify page structure supports multiple product browsing
    await expect(page.locator('body'), 'Page should be structured for multiple product pricing').toContainText(/services|products|aws/i);
  });
});