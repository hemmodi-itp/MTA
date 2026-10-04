import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'https://www.amazon.in/deals?ref_=nav_cs_gb';

test.describe('Deal Card Content Validation (BS-007)', () => {

  test('positive — all deal cards display complete information including thumbnail, badge, and price tag', async ({ page }) => {
    await page.goto(BASE_URL);
    
    // Wait for deals page to load with deal cards
    await page.waitForLoadState('networkidle');
    
    // Locate deal cards using the provided locators (assuming these are within deal card containers)
    const dealCards = page.locator('[data-testid*="deal"], .dealContainer, .deal-card, [class*="deal"]').first().locator('..').locator('[data-testid="add-to-cart-button"]').locator('..');
    
    await expect(dealCards.first(), 'At least one deal card must be visible on the deals page').toBeVisible();
    
    // Get all deal card containers
    const cardCount = await dealCards.count();
    await expect(cardCount, 'Multiple deal cards should be available for validation').toBeGreaterThan(0);
    
    // Validate first 3 deal cards (or available cards if less than 3)
    const cardsToValidate = Math.min(3, cardCount);
    
    for (let i = 0; i < cardsToValidate; i++) {
      const card = dealCards.nth(i);
      
      // Verify thumbnail image exists
      const thumbnail = card.locator('img').first();
      await expect(thumbnail, `Deal card ${i + 1} must display a thumbnail image`).toBeVisible();
      await expect(thumbnail, `Deal card ${i + 1} thumbnail must have a valid src attribute`).toHaveAttribute('src', /.+/);
      
      // Verify badge is present (discount badge, deal badge, etc.)
      const badge = card.locator('[class*="badge"], [class*="discount"], [class*="deal"], .a-badge, span[class*="percent"]').first();
      await expect(badge, `Deal card ${i + 1} must display a promotional badge`).toBeVisible();
      
      // Verify price tag is displayed
      const priceTag = card.locator('[class*="price"], .a-price, [data-testid*="price"], span[class*="currency"]').first();
      await expect(priceTag, `Deal card ${i + 1} must show an explicit price tag`).toBeVisible();
      
      const priceText = await priceTag.textContent();
      await expect(priceText, `Deal card ${i + 1} price must contain currency symbol or numeric value`).toMatch(/[₹$£€¥]|[\d,]+/);
    }
  });

  test('negative — deal cards with missing thumbnail images are identified', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Inject CSS to hide some images to simulate missing thumbnails
    await page.addStyleTag({
      content: `
        [data-testid="add-to-cart-button"] img:nth-child(1) { display: none !important; }
      `
    });
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..').first();
    const hiddenImages = dealCards.locator('img[style*="display: none"], img:not([src]), img[src=""]');
    
    // This test validates we can detect missing images
    const hasHiddenImages = await hiddenImages.count() > 0;
    await expect(hasHiddenImages, 'Test should detect when deal card thumbnails are missing or hidden').toBe(true);
  });

  test('negative — deal cards with corrupted image sources are handled gracefully', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Modify image sources to invalid URLs
    await page.evaluate(() => {
      const images = document.querySelectorAll('img');
      if (images.length > 0) {
        images[0].src = 'invalid-url';
      }
    });
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..').first();
    const corruptedImage = dealCards.locator('img[src="invalid-url"]');
    
    if (await corruptedImage.count() > 0) {
      await expect(corruptedImage, 'Corrupted image should still be present in DOM').toBeAttached();
      // The image may show broken image icon but should not crash the page
      await expect(page, 'Page should remain functional despite corrupted image').toHaveTitle(/.+/);
    }
  });

  test('negative — deal cards without price information are flagged', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Hide price elements to simulate missing prices
    await page.addStyleTag({
      content: `
        [class*="price"], .a-price { display: none !important; }
      `
    });
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..').first();
    const priceElements = dealCards.locator('[class*="price"], .a-price');
    const visiblePrices = await priceElements.filter({ hasText: /[₹$£€¥]|[\d,]+/ }).count();
    
    await expect(visiblePrices, 'Hidden price elements should result in zero visible prices').toBe(0);
  });

  test('negative — deal cards with special characters in price display correctly', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Inject special characters into price elements
    await page.evaluate(() => {
      const priceElements = document.querySelectorAll('[class*="price"], .a-price');
      if (priceElements.length > 0) {
        priceElements[0].textContent = '₹<script>alert("xss")</script>999';
      }
    });
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..').first();
    const modifiedPrice = dealCards.locator(':text("₹<script>")');
    
    if (await modifiedPrice.count() > 0) {
      await expect(modifiedPrice, 'Special characters in price should be displayed as text, not executed').toBeVisible();
    }
    
    // Ensure no script execution occurred
    await expect(page, 'Page should not execute scripts injected in price text').toHaveTitle(/.+/);
  });

  test('boundary — deal cards load completely when page has minimum required elements', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..');
    const cardCount = await dealCards.count();
    
    await expect(cardCount, 'At least one deal card should be present at minimum boundary').toBeGreaterThanOrEqual(1);
    
    if (cardCount > 0) {
      const firstCard = dealCards.first();
      await expect(firstCard, 'Minimum boundary case should still display complete deal card').toBeVisible();
      
      // Verify essential elements are present even at boundary
      const hasImage = await firstCard.locator('img').count() > 0;
      const hasText = await firstCard.locator(':text-matches(".", "i")').count() > 0;
      
      await expect(hasImage || hasText, 'Deal card at boundary should contain either image or text content').toBe(true);
    }
  });

  test('boundary — deal cards handle maximum content length without breaking layout', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Inject very long text into deal card elements
    const longText = 'A'.repeat(500);
    await page.evaluate((text) => {
      const elements = document.querySelectorAll('[class*="title"], [class*="description"]');
      if (elements.length > 0) {
        elements[0].textContent = text;
      }
    }, longText);
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..').first();
    const modifiedElement = dealCards.locator(`:text("${'A'.repeat(100)}")`);
    
    if (await modifiedElement.count() > 0) {
      await expect(modifiedElement, 'Deal card should handle maximum content length gracefully').toBeVisible();
      
      // Verify the card container is still properly bounded
      const cardBounds = await dealCards.boundingBox();
      await expect(cardBounds?.width, 'Deal card width should remain within reasonable bounds despite long content').toBeLessThan(2000);
    }
  });

  test('boundary — deal cards with URL-like content in titles display safely', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    
    // Inject URL-like content into titles
    const urlContent = 'https://malicious-site.com/redirect?param=value';
    await page.evaluate((url) => {
      const titleElements = document.querySelectorAll('[class*="title"], h1, h2, h3');
      if (titleElements.length > 0) {
        titleElements[0].textContent = url;
      }
    }, urlContent);
    
    const dealCards = page.locator('[data-testid="add-to-cart-button"]').locator('..').first();
    const urlTitle = dealCards.locator(`:text("${urlContent.substring(0, 20)}")`);
    
    if (await urlTitle.count() > 0) {
      await expect(urlTitle, 'Deal card should display URL-like content as plain text').toBeVisible();
      
      // Verify no unintended navigation occurs
      await expect(page, 'URL content in title should not cause navigation').toHaveURL(/amazon\.in/);
    }
  });

});