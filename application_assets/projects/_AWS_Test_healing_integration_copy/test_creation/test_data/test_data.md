# Test Data — AWS_Test

Total: **15 dataset(s)**

---

## TD-001: SC-001 — Save Changes

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| enter_element | text | advertisement tracking |
| enter_allow_crosscontext_behavioral_ads | text | yes |
| enter_opt_out_crosscontext_behavioral_ads | text | no |
| enter_im_looking_for | text | privacy settings |
| enter_search | text | data collection preferences |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Empty required fields

**Iteration 1**  
*Expected error: Element field is required*

| Field | Type | Value |
|---|---|---|
| enter_element | text | `""` |
| enter_allow_crosscontext_behavioral_ads | text | yes |
| enter_opt_out_crosscontext_behavioral_ads | text | no |
| enter_im_looking_for | text | privacy settings |
| enter_search | text | data collection preferences |

#### NEG-002 (`boundary`) — Input at maximum field length

**Iteration 1**

| Field | Type | Value |
|---|---|---|
| enter_element | text | this is a very long advertisement tracking preference description that tests the maximum character limit for this input field and should be exactly at the boundary of what is allowed by the system validation rules |
| enter_allow_crosscontext_behavioral_ads | text | yes |
| enter_opt_out_crosscontext_behavioral_ads | text | no |
| enter_im_looking_for | text | privacy settings |
| enter_search | text | data collection preferences |

---

## TD-002: SC-002 — User Login

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_sign_in_target | navigation | sign_in_to_console |
| expected_console_heading | assertion | Sign In to AWS Console |
| expected_login_form | assertion | username |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Sign in console button not found or page fails to load

**Iteration 1**  
*Expected error: Sign in console page failed to load*

| Field | Type | Value |
|---|---|---|
| click_sign_in_target | navigation | sign_in_to_console |
| expected_console_heading | assertion | `""` |
| expected_login_form | assertion | username |

---

## TD-003: SC-003 — Create Account

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_create_account | navigation | create_account_opened |
| expected_url | url | /create-account |
| expected_heading | assertion | Create Account |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Create account button not functional or page fails to load

**Iteration 1**  
*Expected error: Unable to navigate to create account page*

| Field | Type | Value |
|---|---|---|
| click_create_account | navigation | `""` |
| expected_url | url | /error |
| expected_heading | assertion | Page Not Found |

---

## TD-004: SC-004 — User Registration

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_target | navigation | event reinvent 2026 build whats next join us nov 30 to dec 4 in las vegas save 1200 with early bird pricing ends august 25 register today |
| expected_result | assertion | event_reinvent_2026_build_whats_next_join_us_nov_30_to_dec_4_in_las_vegas_save_1200_with_early_bird_pricing_ends_august_25_register_today_opened |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Expected element or content not found after click

**Iteration 1**  
*Expected error: Registration page failed to load or expected content not displayed*

| Field | Type | Value |
|---|---|---|
| click_target | navigation | event reinvent 2026 build whats next join us nov 30 to dec 4 in las vegas save 1200 with early bird pricing ends august 25 register today |
| expected_result | assertion | `""` |

---

## TD-005: SC-005 — Search Products

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_target | navigation | industrial siemens mobility turns 175 years of data into searchable insights with aws ai view the story |
| expected_url | url | industrial_siemens_mobility_turns_175_years_of_data_into_searchable_insights_with_aws_ai_view_the_story |
| expected_heading | assertion | Siemens Mobility turns 175 years of data into searchable insights with AWS AI |
| expected_content | assertion | View the story |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation target not found or content missing

**Iteration 1**  
*Expected error: Page not found or content unavailable*

| Field | Type | Value |
|---|---|---|
| click_target | navigation | industrial siemens mobility turns 175 years of data into searchable insights with aws ai view the story |
| expected_url | url | 404 |
| expected_heading | assertion | `""` |
| expected_content | assertion | `""` |

---

## TD-006: SC-006 — User Sign In

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_target | navigation | government solutions designed to help government agencies modernize meet mandates reduce costs and deliver mission outcomes view industry |
| expected_heading | assertion | Government Solutions |
| expected_content | assertion | modernize meet mandates reduce costs |
| expected_url_fragment | url | /government-solutions |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation target not found or content missing

**Iteration 1**  
*Expected error: Page content failed to load or heading not found*

| Field | Type | Value |
|---|---|---|
| click_target | navigation | government solutions designed to help government agencies modernize meet mandates reduce costs and deliver mission outcomes view industry |
| expected_heading | assertion | `""` |
| expected_content | assertion | modernize meet mandates reduce costs |
| expected_url_fragment | url | /government-solutions |

---

## TD-007: SC-007 — Add Item

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_target | navigation | telecommunications accelerate innovation scale with confidence and add agility with cloudbased telecom solutions view industry |
| expected_page_content | assertion | telecommunications_accelerate_innovation_scale_with_confidence_and_add_agility_with_cloudbased_telecom_solutions_view_industry_opened |
| expected_heading | assertion | Telecommunications Solutions |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation target not found or page fails to load

**Iteration 1**  
*Expected error: Navigation failed - target section not accessible*

| Field | Type | Value |
|---|---|---|
| click_target | navigation | telecommunications accelerate innovation scale with confidence and add agility with cloudbased telecom solutions view industry |
| expected_page_content | assertion | `""` |
| expected_heading | assertion | Page Not Found |

---

## TD-008: SC-008 — Create Account

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_create_account | navigation | create_an_aws_account_opened |
| expected_page_title | assertion | Create AWS Account |
| expected_url_fragment | url | /create-account |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Account creation page fails to load or navigation error

**Iteration 1**  
*Expected error: Page not found or navigation failed*

| Field | Type | Value |
|---|---|---|
| click_create_account | navigation | page_not_found |
| expected_page_title | assertion | `""` |
| expected_url_fragment | url | /404 |

---

## TD-009: SC-009 — Browse AWS_Test

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_target_section | navigation | AWS_Test interface |
| expected_filter_button | assertion | filter all |
| expected_contact_link | assertion | contact us |
| expected_story_content | assertion | agentic ai data leaders |
| min_industry_sections | count_min | 6 |
| expected_page_url | url | /aws-test |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key navigation elements missing or incorrect

**Iteration 1**  
*Expected error: Filter button not found or not clickable*

| Field | Type | Value |
|---|---|---|
| navigate_target_section | navigation | AWS_Test interface |
| expected_filter_button | assertion | `""` |
| expected_contact_link | assertion | contact us |
| expected_story_content | assertion | agentic ai data leaders |
| min_industry_sections | count_min | 6 |
| expected_page_url | url | /aws-test |

---

## TD-010: SC-010 — Interact with AWS_Test

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_target | navigation | accept |
| expected_page_title | assertion | AWS_Test |
| expected_button_visible | assertion | Start free with AWS |
| min_navigation_elements | count_min | 10 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Target element not found or page elements missing

**Iteration 1**  
*Expected error: Element not found or page failed to load properly*

| Field | Type | Value |
|---|---|---|
| click_target | navigation | nonexistent_element |
| expected_page_title | assertion | AWS_Test |
| expected_button_visible | assertion | `""` |
| min_navigation_elements | count_min | 0 |

---

## TD-011: M01_BS_001 — Navigate using navigation bar to fetch page information

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_navigation_element | navigation | Products |
| expected_page_heading | assertion | AWS Products and Services |
| expected_page_content | assertion | Explore our comprehensive cloud computing services |
| expected_url_fragment | url | /products |
| min_service_cards | count_min | 5 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation element missing or page content not loaded

**Iteration 1**  
*Expected error: Page heading not found or failed to load*

| Field | Type | Value |
|---|---|---|
| click_navigation_element | navigation | Products |
| expected_page_heading | assertion | `""` |
| expected_page_content | assertion | Explore our comprehensive cloud computing services |
| expected_url_fragment | url | /products |
| min_service_cards | count_min | 5 |

---

## TD-012: M01_BS_002 — Browse new AWS items in What's New section

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | What's New |
| expected_section_heading | assertion | What's New with AWS |
| min_new_items_count | count_min | 5 |
| expected_item_category | assertion | AWS Services |
| click_item_title | assertion | Amazon EC2 M7i instances |
| expected_detail_url | url | /about-aws/whats-new/2023/ |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — What's New section unavailable or content missing

**Iteration 1**  
*Expected error: What's New section is currently unavailable*

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | What's New |
| expected_section_heading | assertion | `""` |
| min_new_items_count | count_min | 0 |
| expected_item_category | assertion | `""` |
| click_item_title | assertion | `""` |
| expected_detail_url | url | /404 |

---

## TD-013: M01_BS_003 — View client images through image carousel

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_carousel_section | navigation | client-showcase-carousel |
| expected_carousel_heading | assertion | Our Trusted Clients |
| expected_client_images | assertion | Netflix, Airbnb, Spotify |
| min_carousel_items_count | count_min | 3 |
| expected_navigation_controls | assertion | Previous, Next, Indicators |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Carousel content not loaded or missing

**Iteration 1**  
*Expected error: Carousel failed to load client images*

| Field | Type | Value |
|---|---|---|
| navigate_carousel_section | navigation | client-showcase-carousel |
| expected_carousel_heading | assertion | `""` |
| expected_client_images | assertion | `""` |
| min_carousel_items_count | count_min | 0 |
| expected_navigation_controls | assertion | `""` |

---

## TD-014: M01_BS_004 — Browse customer success stories through story cards

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | Customer Story Cards |
| expected_cards_visible | assertion | customer success stories |
| min_story_cards_count | count_min | 3 |
| click_story_card | navigation | Netflix Case Study |
| expected_story_content | assertion | customer testimonials and success cases |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Customer Story Cards section not available or content missing

**Iteration 1**  
*Expected error: Customer story cards are not available or failed to load*

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | Customer Story Cards |
| expected_cards_visible | assertion | `""` |
| min_story_cards_count | count_min | 0 |
| click_story_card | navigation | Netflix Case Study |
| expected_story_content | assertion | `""` |

---

## TD-015: M01_BS_005 — Return to top of page using back to top functionality

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | top |
| expected_back_to_top_button | assertion | Back to top |
| expected_header_visible | assertion | AWS |
| expected_url_fragment | url | #top |
| scroll_position_y | assertion | 0 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Back to top button not found or navigation fails

**Iteration 1**  
*Expected error: Back to top button not found*

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | top |
| expected_back_to_top_button | assertion | `""` |
| expected_header_visible | assertion | AWS |
| expected_url_fragment | url | #top |
| scroll_position_y | assertion | 0 |

---
