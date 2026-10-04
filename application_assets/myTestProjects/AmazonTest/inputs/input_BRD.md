# Business Requirements Document
## Test Suite for amazon.in/deals

## 1. Purpose

This Business Requirements Document (BRD) defines the comprehensive testing requirements for the Amazon India Deals ("Today's Deals") landing page. The page serves as a primary driver of user conversion, showcasing time-sensitive discounts, deal categories, lightning deals, and personalized offers. The primary objective of this test suite is to validate that the dynamic content filters, deal cards, countdown timers, infinite scroll/pagination, and checkout funnels operate flawlessly across varying viewports and browsers, ensuring an uninterrupted and high-converting user journey.

---

## 2. Page Structure Overview

The `/deals` page is a highly dynamic, widget-driven e-commerce page with the following primary structural regions:

| Region | Description |
|---|---|
| Global Header / Navbar | Amazon logo, delivery location selector, search bar, department dropdown, prime/miniTV shortcuts, account lists, orders, and shopping cart. |
| Category/Deals Navigation Bar | Horizontal sub-navigation specific to deals (e.g., "Today's Deals", "Flash Sales", "Coupons", "Watched Deals"). |
| Banner / Hero Carousel | Seasonal promotional banners or marquee marketing sliders highlighting major sales events (e.g., Great Indian Festival). |
| Left-Hand Filter Panel | Faceted navigation containing filters for Category, Deal Type (Lightning Deals, Deal of the Day), Price, Discount Range, Average Customer Review, and Availability. |
| Main Deal Grid | Responsive grid containing deal cards layout. Each card features product image, discount tag, price metadata, countdown timers, and contextual CTAs. |
| Pagination / Infinite Scroll Control | Bottom controls to navigate across multiple deal pages or handle dynamic lazy loading. |
| Global Footer | Multilayered links covering "Get to Know Us", "Connect with Us", "Make Money with Us", "Let Us Help You", legal/copyright notices, and country selectors. |

---

## 3. Actors

| Actor | Description |
|---|---|
| Visitor (anonymous) | Unauthenticated user browsing active promotions, sorting deals, and exploring categories. |
| Logged-In Customer | Authenticated user with saved delivery addresses, prime eligibility, personalized deal feeds, and historical "Watched Deals". |
| Prime Member | Premium authenticated tier entitled to early access for select Lightning Deals and exclusive Prime-only pricing. |
| Automated Test Agent | The automated execution framework (Playwright, Selenium, Cypress) driving UI actions and API intercept verifications. |

---

## 4. Business Rules

### BR-01 — Real-Time Deal Availability and Inventory Updates
All displayed deals must accurately reflect their structural availability. If an item becomes 100% claimed (specifically Lightning Deals), the card UI must immediately update to reflect a "Join Waitlist" or "Ended" state, disabling the primary "Add to Cart" CTA.

### BR-02 — Dynamic Price/Discount Transparency
Every deal card must visually convey the following metrics: the final deal price, the original list price (crossed out), the exact percentage savings, and clear labeling if an offer is a "Lightning Deal" or "Deal of the Day".

### BR-03 — Viewport and Multi-Device Compatibility
The grid layout must remain perfectly responsive. The column matrix must dynamically shift down from desktop (4–5 items per row) to tablet (2-3 items) and mobile viewport layouts (1-2 items per row) without any horizontal scroll bar generation or text/image asset truncation.

### BR-04 — User Session and Location-Based Filtering
Deal selection, tax parameters, and shipping availability displayed on the `/deals` canvas must respect the selected postal pincode active in the Global Header.

### BR-05 — Multi-Faceted Filter Compounding
The left-hand filter attributes must be cumulative and multi-selectable. Checking multiple filters simultaneously (e.g., Category: Electronics + Discount: 30% Off or More) must trigger an asynchronous page update (AJAX) returning only items matching all combined parameters.

### BR-06 — Time-Bound Lightning Deal Countdowns
Any item marked as a "Lightning Deal" must feature a functional, real-time descending countdown clock. Once the clock hits `00:00:00`, the deal must expire instantly, reverting the item price to standard or hiding the deal card on the subsequent refresh.

### BR-07 — Cart Integration and Claim Timer Reservation
Clicking "Add to Cart" directly from a Lightning Deal card must initiate a 15-minute reservation timer inside the global shopping cart. If the purchase is not completed within 15 minutes, the deal discount must drop off automatically.

---

## 5. User Workflows

### Workflow 1 — Filter-Driven Product Discovery
User lands on `/deals`, modifies their delivery location to verify shipping, navigates to the left-hand panel, filters down by "Mobiles & Accessories", sorts by "Discount - High to Low", and expands a card to investigate detailed terms.
**Expected Path:** `/deals` → Pincode Selector Update → Category Filter Check → Sort Dropdown Interaction → Dynamic Grid Re-render.

### Workflow 2 — Lightning Deal Checkout Sprint
A logged-in customer monitors an upcoming Lightning Deal. The deal opens; they click "Add to Cart" instantly from the deals dashboard, watch the cart item count increment to 1, and proceed straight to checkout.
**Expected Path:** `/deals` → Locate Lightning Deal Card → Click "Add to Cart" → Cart Badge Increments → Click "Proceed to Buy" → Navigate to Secure Checkout Gateway.

### Workflow 3 — Cross-Category Navigation
User browses deals, decides to explore standard department listings instead, clicks the "Best Sellers" link in the global navbar or a specific footer category, and safely exits the deals sub-domain.
**Expected Path:** `/deals` → Global Navbar Element → Click "Best Sellers" → Land on `/gp/bestsellers/`.

### Workflow 4 — Waitlist Onboarding
User discovers an active high-demand deal that is already 100% claimed but has an active waitlist availability. They click "Join Waitlist", the button transitions to "In Waitlist", and an alert condition is primed for processing when inventory reallocates.
**Expected Path:** `/deals` → Fully Claimed Lightning Deal Card → Click "Join Waitlist" → CTA Label Changes to "In Waitlist".

---

## 6. Test Scenarios

### Module 1 — Page Load, Presentation, and Responsiveness

| ID | Scenario | Priority |
|---|---|---|
| TC-001 | Page returns HTTP 200 status code and successfully paints core layout regions without console faults. | Critical |
| TC-002 | Page `<title>` contains appropriate localized localized branding strings (e.g., "Amazon.in Today's Deals"). | High |
| TC-003 | Banners and primary hero carousels load distinct visual assets without image breakage. | Medium |
| TC-004 | Left-hand filter framework displays complete selector options (Categories, Deal Type, Discount). | Critical |
| TC-005 | Grid components adjust perfectly to 1280px (Desktop) viewport without horizontal overflow. | High |
| TC-006 | Grid components collapse cleanly to 768px (Tablet) viewport with functional, un-overlapped text. | High |
| TC-007 | Grid transforms to 375px (Mobile) viewport with stacked layout structures and readable font sizes. | High |
| TC-008 | Lazy loading / infinite scroll functions reliably, loading subsequent deal sets on scrolling down. | High |

---

### Module 2 — Filter Framework and Sorting Operations

| ID | Scenario | Priority |
|---|---|---|
| TC-009 | Selecting a single category checkbox correctly narrows the main grid results to that category. | Critical |
| TC-010 | Selecting multiple overlapping filters (e.g., "Computers" + "Over 50% Off") displays the correct intersection. | High |
| TC-011 | Clearing an active filter pill dynamically resets the grid to its broader previous parent selection state. | High |
| TC-012 | Interacting with the "Sort By" dropdown menu (Price: Low to High) structurally rearranges the grid order. | Critical |
| TC-013 | Selecting the "Prime Early Access Deals" filter restricts the viewport feed strictly to Prime exclusive listings. | Critical |
| TC-014 | Inputting an explicit min/max price range filter displays only items conforming to that numerical boundary. | Medium |

---

### Module 3 — Deal Card UI & Call-to-Actions (CTAs)

| ID | Scenario | Priority |
|---|---|---|
| TC-015 | Each deal card shows an item thumbnail image, a badge (e.g., "Deal of the Day"), and an explicit price tag. | Critical |
| TC-016 | Active Lightning Deal cards display a dynamic progress bar showing the accurate percentage of items claimed. | High |
| TC-017 | Clicking a deal image or title text successfully navigates the user directly to the Product Detail Page (PDP). | Critical |
| TC-018 | The "Add to Cart" CTA on a standard deal card increments the global shopping cart summary instantly. | Critical |
| TC-019 | When a Lightning Deal hits 100% claimed, the CTA transitions to "Join Waitlist" or displays a "Sold Out" state. | High |
| TC-020 | Pressing the browser "Back" button from a PDP successfully restores the precise scrolled filter state on `/deals`. | Medium |

---

### Module 4 — Core Global Integrations (Header & Footer)

| ID | Scenario | Priority |
|---|---|---|
| TC-021 | Changing the delivery pincode in the global header updates the active deals based on regional fulfillment. | Critical |
| TC-022 | The Search bar within the deals page operates properly, transferring terms into the general store index. | High |
| TC-023 | Global Navbar menu links (e.g., "Mobiles", "Customer Service") map correctly to target store channels. | High |
| TC-024 | Footer social, legal, and operational corporate anchors point to valid destinations. | Medium |
| TC-025 | All external corporate links mapped within the footer open safely using `target="_blank"` attributes. | Medium |

---

### Module 5 — Keyboard Navigation and Accessibility (A11y)

| ID | Scenario | Priority |
|---|---|---|
| TC-026 | Users can sequential-tab smoothly through all interactive category filters and deal cards. | High |
| TC-027 | Focused buttons, links, and input boxes reveal high-contrast visual focus indicators. | Medium |
| TC-028 | Image components within cards carry functional `alt` attributes for screen readers. | High |

---

## 7. Interaction / Movement Catalogue

| Movement Type | Target UI Element | Execution Call | Expected Automation Result |
|---|---|---|---|
| Click | Category Checkbox | `click()` | Updates grid via AJAX; item count matches filter. |
| Click | "Add to Cart" Button | `click()` | Element text changes to "Adding/Added"; global cart count +1. |
| Click | Deal Card Title | `click()` | Browser window redirects to corresponding product PDP. |
| Click | "Join Waitlist" CTA | `click()` | Button state morphs to "In Waitlist" with alert capability. |
| Selection | Sort Dropdown Menu | `select_option()` | DOM re-orders grid components by selected criteria. |
| Hover | Product Deal Card | `hover()` | Elevation shadow accentuates card or shows quick-view overlay. |
| Scroll | Window Viewport | `scroll_to_bottom()` | Triggers asynchronous network call loading additional deal elements. |
| Viewport Resize| Window Dimensions | `set_viewport_size()` | Layout shifts grid matrix cleanly across 375px/768px/1280px. |
| Keyboard Entry | Pincode Field | `fill("110001")` | Field accepts values and prompts location rewrite actions. |

---

## 8. Out of Scope

- Validating payment processing, bank discounts, or credit card check verification steps during downstream checkout.
- Testing product listings, reviews, variant selections, or QA modules on the individual Product Detail Pages (PDP).
- Simulating server failures, inventory drops, or network connection timeouts on downstream Amazon systems.
- Executing internal warehouse management system checks or supply chain logistical verification testing.
- Reviewing localized text accuracy across all available vernacular translations of the site (e.g., Hindi, Tamil translations).

---

## 9. Test Data Requirements

| Data Entity | Technical Parameter / Value Range |
|---|---|
| Target Base URL | `https://www.amazon.in` |
| Route Under Test | `/deals` or `/deals?ref_=nav_cs_gb` |
| Valid Delivery Pincodes | New Delhi: `110001`, Mumbai: `400001`, Bengaluru: `560001` |
| Primary Filtering Terms | `Mobiles & Accessories`, `Electronics`, `Home & Kitchen` |
| Target Viewport Layouts | Desktop: `1280x800`, Tablet: `768x1024`, Mobile: `375x812` |
| Platform Grid Standards | Chrome (Latest stable), Firefox (Latest stable), Safari/WebKit (Latest stable) |
| Test Accounts | Valid Non-Prime Account, Valid Prime Member Account |

---

## 10. Acceptance Criteria

The Amazon India Deals automated test validation run is considered successful and signed off when:
1. **100% Passing Rate** across all classified "Critical" priority validation pathways.
2. Minimum of **95% Passing Rate** across all classified "High" priority validation test scripts.
3. Asynchronous lazy loading operations complete without throwing broken grid layouts or structural layout failures.
4. Filter state compounding does not trigger endless loaders or unexpected 404 page faults.
5. All external corporate link anchors located in the footer structure open correctly in detached browser tabs.