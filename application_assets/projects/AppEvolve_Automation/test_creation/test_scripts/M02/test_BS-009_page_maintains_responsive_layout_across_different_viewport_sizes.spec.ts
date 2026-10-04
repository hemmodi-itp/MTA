import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard';

test.describe('Page maintains responsive layout across different viewport sizes (BS-009)', () => {

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
  test('positive — page layout remains functional across mobile, tablet, and desktop viewports', async ({ page }) => {
    // Load page at mobile viewport (375px)
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Verify layout does not break or overflow horizontally at mobile
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const bodyClientWidth = await page.evaluate(() => document.body.clientWidth);
    await expect(bodyScrollWidth <= 375, 'Page should not have horizontal overflow at mobile viewport (375px)').toBeTruthy();
    
    const mainContent = page.locator('body');
    await expect(mainContent, 'Main content should be visible at mobile viewport').toBeVisible();

    // Resize viewport to tablet (768px)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500); // Allow layout to adjust

    // Verify layout remains intact without horizontal overflow at tablet
    const tabletScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    await expect(tabletScrollWidth <= 768, 'Page should not have horizontal overflow at tablet viewport (768px)').toBeTruthy();
    await expect(mainContent, 'Main content should remain visible at tablet viewport').toBeVisible();

    // Resize viewport to desktop (1280px)
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.waitForTimeout(500); // Allow layout to adjust

    // Confirm layout is properly rendered without overflow at desktop
    const desktopScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    await expect(desktopScrollWidth <= 1280, 'Page should not have horizontal overflow at desktop viewport (1280px)').toBeTruthy();
    await expect(mainContent, 'Main content should remain visible at desktop viewport').toBeVisible();

    // Verify navigation elements are accessible across all viewports
    const navigation = page.locator('nav, [role="navigation"], header');
    if (await navigation.count() > 0) {
      await expect(navigation.first(), 'Navigation should be accessible at desktop viewport').toBeVisible();
    }
  });

  test('negative — extremely narrow viewport causes layout degradation', async ({ page }) => {
    // Set viewport to unreasonably narrow width
    await page.setViewportSize({ width: 200, height: 667 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Check if content becomes inaccessible or severely broken
    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const hasHorizontalScroll = bodyScrollWidth > 200;
    
    // At very narrow widths, some horizontal scroll might be expected
    const mainContent = page.locator('body');
    await expect(mainContent, 'Page body should still be present even at extremely narrow viewport').toBeVisible();
    
    // Verify critical elements don't completely disappear
    const visibleElements = await page.locator('*:visible').count();
    await expect(visibleElements > 0, 'At least some elements should remain visible at narrow viewport').toBeTruthy();
  });

  test('negative — extremely wide viewport reveals layout issues', async ({ page }) => {
    // Set viewport to very wide width
    await page.setViewportSize({ width: 3840, height: 2160 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const mainContent = page.locator('body');
    await expect(mainContent, 'Main content should be visible at ultra-wide viewport').toBeVisible();

    // Check if layout stretches inappropriately or becomes unreadable
    const bodyWidth = await page.evaluate(() => document.body.offsetWidth);
    const contentContainers = page.locator('main, .container, .content, [role="main"]');
    
    if (await contentContainers.count() > 0) {
      const containerWidth = await contentContainers.first().evaluate(el => el.offsetWidth);
      // Content should have reasonable max-width, not stretch to full ultra-wide screen
      await expect(containerWidth < 3840, 'Content containers should not stretch to full ultra-wide viewport').toBeTruthy();
    }
  });

  test('negative — rapid viewport size changes cause layout instability', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Rapidly change viewport sizes
    const viewportSizes = [
      { width: 375, height: 667 },
      { width: 1920, height: 1080 },
      { width: 768, height: 1024 },
      { width: 320, height: 568 },
      { width: 1280, height: 720 }
    ];

    for (const size of viewportSizes) {
      await page.setViewportSize(size);
      await page.waitForTimeout(100); // Minimal wait to simulate rapid changes
      
      const mainContent = page.locator('body');
      await expect(mainContent, `Page should remain stable during rapid resize to ${size.width}x${size.height}`).toBeVisible();
    }

    // Final check that layout is still functional
    const finalScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const finalViewportWidth = await page.evaluate(() => window.innerWidth);
    await expect(finalScrollWidth <= finalViewportWidth + 20, 'Layout should stabilize after rapid viewport changes').toBeTruthy();
  });

  test('negative — portrait orientation on tablet reveals layout issues', async ({ page }) => {
    // Set tablet in portrait mode (narrow but tall)
    await page.setViewportSize({ width: 768, height: 1366 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const mainContent = page.locator('body');
    await expect(mainContent, 'Main content should be visible in tablet portrait mode').toBeVisible();

    // Check for horizontal overflow in portrait tablet mode
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    await expect(scrollWidth <= 768, 'Page should not overflow horizontally in tablet portrait mode').toBeTruthy();

    // Verify navigation and key elements are still accessible
    const interactiveElements = page.locator('button, a, input, [role="button"]');
    if (await interactiveElements.count() > 0) {
      const firstInteractive = interactiveElements.first();
      await expect(firstInteractive, 'Interactive elements should remain accessible in portrait tablet mode').toBeVisible();
    }
  });

  test('boundary — minimum supported viewport width maintains usability', async ({ page }) => {
    // Test at the boundary of minimum supported mobile width (320px)
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const mainContent = page.locator('body');
    await expect(mainContent, 'Main content should be visible at minimum supported width (320px)').toBeVisible();

    // Verify no horizontal overflow at minimum width
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    await expect(scrollWidth <= 320, 'Page should not have horizontal overflow at minimum supported width').toBeTruthy();

    // Check that essential functionality remains accessible
    const clickableElements = page.locator('button, a, [role="button"]');
    if (await clickableElements.count() > 0) {
      const elementBounds = await clickableElements.first().boundingBox();
      if (elementBounds) {
        await expect(elementBounds.width > 0 && elementBounds.height > 0, 'Interactive elements should have proper dimensions at minimum width').toBeTruthy();
      }
    }
  });

  test('boundary — maximum common desktop width handles content appropriately', async ({ page }) => {
    // Test at high-end desktop resolution (1920px)
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const mainContent = page.locator('body');
    await expect(mainContent, 'Main content should be visible at maximum common desktop width (1920px)').toBeVisible();

    // Verify layout utilizes space effectively without becoming too sparse
    const contentElements = page.locator('main, .content, [role="main"], article, section');
    if (await contentElements.count() > 0) {
      const contentBounds = await contentElements.first().boundingBox();
      if (contentBounds) {
        // Content should not be too narrow on wide screens
        await expect(contentBounds.width >= 800, 'Content should utilize reasonable width on large desktop screens').toBeTruthy();
        // But also should not stretch to full width unreasonably
        await expect(contentBounds.width <= 1600, 'Content should not stretch excessively on large desktop screens').toBeTruthy();
      }
    }
  });

  test('boundary — tablet landscape breakpoint maintains layout integrity', async ({ page }) => {
    // Test at common tablet landscape resolution (1024px)
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const mainContent = page.locator('body');
    await expect(mainContent, 'Main content should be visible at tablet landscape width (1024px)').toBeVisible();

    // Verify no horizontal overflow at tablet landscape
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    await expect(scrollWidth <= 1024, 'Page should not have horizontal overflow at tablet landscape width').toBeTruthy();

    // Check that layout transitions properly between tablet and desktop breakpoints
    const navigation = page.locator('nav, [role="navigation"], header nav');
    if (await navigation.count() > 0) {
      await expect(navigation.first(), 'Navigation should be properly displayed at tablet landscape breakpoint').toBeVisible();
    }

    // Verify touch-friendly element sizing is maintained
    const buttons = page.locator('button, [role="button"]');
    if (await buttons.count() > 0) {
      const buttonBounds = await buttons.first().boundingBox();
      if (buttonBounds) {
        await expect(buttonBounds.height >= 32, 'Interactive elements should maintain touch-friendly size at tablet landscape').toBeTruthy();
      }
    }
  });

});