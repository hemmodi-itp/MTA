# Test Data — AWS_Test

Total: **46 dataset(s)**

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

## TD-016: M02_BS_001 — User navigates Aurora page using navigation bar

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | About Aurora |
| click_navigation_element | navigation | Features |
| expected_page_heading | assertion | Aurora Platform Overview |
| expected_content_keyword | assertion | navigation |
| expected_url_fragment | url | /aurora/features |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation element not found or content missing

**Iteration 1**  
*Expected error: Page heading not found or content failed to load*

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | About Aurora |
| click_navigation_element | navigation | Features |
| expected_page_heading | assertion | `""` |
| expected_content_keyword | assertion | navigation |
| expected_url_fragment | url | /aurora/features |

---

## TD-017: M02_BS_002 — User reads Aurora introduction information

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_to_section | navigation | What is Aurora |
| expected_heading | assertion | What is Aurora |
| expected_description_content | assertion | Aurora is a comprehensive platform that provides users with advanced features and capabilities |
| expected_url_fragment | url | #what-is-aurora |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Required Aurora section content is missing or incorrect

**Iteration 1**  
*Expected error: Aurora section heading not found*

| Field | Type | Value |
|---|---|---|
| scroll_to_section | navigation | What is Aurora |
| expected_heading | assertion | `""` |
| expected_description_content | assertion | Aurora is a comprehensive platform that provides users with advanced features and capabilities |
| expected_url_fragment | url | #what-is-aurora |

**Iteration 2**  
*Expected error: Aurora description content not found*

| Field | Type | Value |
|---|---|---|
| scroll_to_section | navigation | What is Aurora |
| expected_heading | assertion | What is Aurora |
| expected_description_content | assertion | `""` |
| expected_url_fragment | url | #what-is-aurora |

---

## TD-018: M02_BS_003 — User explores Aurora benefits information

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_benefits_section | navigation | Benefits of Aurora |
| expected_benefits_heading | assertion | Benefits of Aurora |
| expected_benefit_content | assertion | advantages and value proposition |
| min_benefits_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Benefits section or content not available

**Iteration 1**  
*Expected error: Benefits section heading not found*

| Field | Type | Value |
|---|---|---|
| navigate_benefits_section | navigation | Benefits of Aurora |
| expected_benefits_heading | assertion | `""` |
| expected_benefit_content | assertion | advantages and value proposition |
| min_benefits_count | count_min | 3 |

---

## TD-019: M02_BS_004 — User views customer success stories

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_target | navigation | Customer Story Cards section |
| expected_heading | assertion | Customer Success Stories |
| click_story_card | navigation | individual story card |
| expected_testimonial_content | assertion | detailed testimonials |
| min_story_cards_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Customer Stories section missing or content not loaded

**Iteration 1**  
*Expected error: Customer stories content failed to load*

| Field | Type | Value |
|---|---|---|
| scroll_target | navigation | Customer Story Cards section |
| expected_heading | assertion | `""` |
| click_story_card | navigation | individual story card |
| expected_testimonial_content | assertion | `""` |
| min_story_cards_count | count_min | 0 |

---

## TD-020: M02_BS_005 — User follows Get Started with Aurora workflow

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| expected_redirect_url | url | https://aws.amazon.com/rds/aurora/resources/ |
| scroll_target_section | navigation | search field |
| search_user_guide | assertion | User Guide |
| expected_user_guide_card | assertion | User Guide card |
| min_guide_results | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — User Guide content not available or search fails

**Iteration 1**  
*Expected error: User Guide card not found or search returned no results*

| Field | Type | Value |
|---|---|---|
| expected_redirect_url | url | https://aws.amazon.com/rds/aurora/resources/ |
| scroll_target_section | navigation | search field |
| search_user_guide | assertion | User Guide |
| expected_user_guide_card | assertion | `""` |
| min_guide_results | count_min | 0 |

---

## TD-021: M02_BS_006 — User explores Aurora pricing information

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_pricing_section | navigation | Pricing |
| scroll_target_section | navigation | Additional features and costs |
| expected_expandable_sections | count_min | 16 |
| expected_expand_control | assertion | + sign |
| expected_collapse_control | assertion | - sign |
| expected_pricing_content | assertion | detailed pricing information |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key pricing section not found or unavailable

**Iteration 1**  
*Expected error: Additional features and costs section not found or expandable controls unavailable*

| Field | Type | Value |
|---|---|---|
| navigate_pricing_section | navigation | Pricing |
| scroll_target_section | navigation | Additional features and costs |
| expected_expandable_sections | count_min | 0 |
| expected_expand_control | assertion | `""` |
| expected_collapse_control | assertion | `""` |
| expected_pricing_content | assertion | `""` |

---

## TD-022: M02_BS_007 — Guest user explores Aurora product features

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_to_aurora_page | url | /aurora |
| expected_product_heading | assertion | Amazon Aurora |
| browse_showcase_section | navigation | product-showcase |
| expected_features_content | assertion | High Performance |
| min_feature_items | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Missing or corrupted product content

**Iteration 1**  
*Expected error: Product heading not found on page*

| Field | Type | Value |
|---|---|---|
| navigate_to_aurora_page | url | /aurora |
| expected_product_heading | assertion | `""` |
| browse_showcase_section | navigation | product-showcase |
| expected_features_content | assertion | High Performance |
| min_feature_items | count_min | 3 |

---

## TD-023: M02_BS_008 — Logged in user accesses Aurora product information

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_aurora_page | navigation | Aurora product page |
| expected_page_title | assertion | Aurora - Product Information |
| expected_description_section | assertion | Aurora Description |
| expected_benefits_section | assertion | Aurora Benefits |
| min_customer_stories | count_min | 3 |
| expected_url_fragment | url | /products/aurora |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key product sections missing or incorrect

**Iteration 1**  
*Expected error: Page title not found or empty*

| Field | Type | Value |
|---|---|---|
| navigate_aurora_page | navigation | Aurora product page |
| expected_page_title | assertion | `""` |
| expected_description_section | assertion | Aurora Description |
| expected_benefits_section | assertion | Aurora Benefits |
| min_customer_stories | count_min | 3 |
| expected_url_fragment | url | /products/aurora |

---

## TD-024: M02_BS_009 — User executes automated workflows successfully

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| initiate_workflow_name | assertion | Get Started with Aurora |
| verify_first_completion | assertion | Workflow completed successfully |
| execute_pricing_workflow | assertion | Pricing exploration workflow |
| confirm_second_completion | assertion | Workflow completed successfully |
| expected_workflow_status | assertion | Both workflows executed without errors |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Workflow execution fails or incomplete

**Iteration 1**  
*Expected error: One or more automated workflows failed to execute successfully*

| Field | Type | Value |
|---|---|---|
| initiate_workflow_name | assertion | Get Started with Aurora |
| verify_first_completion | assertion | Workflow failed to complete |
| execute_pricing_workflow | assertion | Pricing exploration workflow |
| confirm_second_completion | assertion | Workflow failed to complete |
| expected_workflow_status | assertion | Workflow execution error occurred |

---

## TD-025: M02_BS_010 — System executes all automated test cases

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| execute_test_case_one | assertion | Test Case 1: PASSED |
| execute_test_case_two | assertion | Test Case 2: PASSED |
| execute_test_case_three | assertion | Test Case 3: PASSED |
| execute_test_case_four | assertion | Test Case 4: PASSED |
| execute_test_case_five | assertion | Test Case 5: PASSED |
| verify_test_results | assertion | All automated test cases completed successfully |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Test case execution failure

**Iteration 1**  
*Expected error: Automated test suite execution failed - not all test cases passed*

| Field | Type | Value |
|---|---|---|
| execute_test_case_one | assertion | Test Case 1: FAILED |
| execute_test_case_two | assertion | Test Case 2: PASSED |
| execute_test_case_three | assertion | Test Case 3: PASSED |
| execute_test_case_four | assertion | Test Case 4: PASSED |
| execute_test_case_five | assertion | Test Case 5: PASSED |
| verify_test_results | assertion | 1 test case failed validation criteria |

---

## TD-026: M03_BS_007 — Browse AWS Aurora pricing page with navigation to different pricing models

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_pricing_section | navigation | AWS Aurora pricing product showcase |
| locate_navigation_bar | assertion | pricing models navigation bar |
| expected_on_demand_pricing | assertion | On-Demand pricing information |
| expected_reserved_pricing | assertion | Reserved Instance pricing information |
| expected_serverless_pricing | assertion | Aurora Serverless pricing information |
| min_pricing_models_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key pricing content missing or navigation fails

**Iteration 1**  
*Expected error: Navigation bar for pricing models not found*

| Field | Type | Value |
|---|---|---|
| navigate_pricing_section | navigation | AWS Aurora pricing product showcase |
| locate_navigation_bar | assertion | `""` |
| expected_on_demand_pricing | assertion | On-Demand pricing information |
| expected_reserved_pricing | assertion | Reserved Instance pricing information |
| expected_serverless_pricing | assertion | Aurora Serverless pricing information |
| min_pricing_models_count | count_min | 3 |

---

## TD-027: M03_BS_008 — Access Understand Pricing section to learn how to get started

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | Understand Pricing |
| expected_heading | assertion | How to get started |
| expected_guidance_content | assertion | getting started guidance |
| expected_url_fragment | url | /pricing#understand-pricing |
| min_guidance_items | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Required section or content not found on page

**Iteration 1**  
*Expected error: Getting started heading not found in Understand Pricing section*

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | Understand Pricing |
| expected_heading | assertion | `""` |
| expected_guidance_content | assertion | getting started guidance |
| expected_url_fragment | url | /pricing#understand-pricing |
| min_guidance_items | count_min | 3 |

---

## TD-028: M03_BS_009 — Review payment options in How to Pay section

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | How to Pay |
| expected_heading | assertion | How to Pay |
| expected_payment_methods | assertion | Credit Card, Bank Transfer, AWS Credits, Direct Debit |
| expected_descriptions_visible | assertion | Payment method descriptions and details |
| min_payment_options_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Payment section not found or empty

**Iteration 1**  
*Expected error: How to Pay section not found or payment options not displayed*

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | How to Pay |
| expected_heading | assertion | `""` |
| expected_payment_methods | assertion | `""` |
| expected_descriptions_visible | assertion | `""` |
| min_payment_options_count | count_min | 0 |

---

## TD-029: M03_BS_010 — Browse pricing information for multiple AWS products

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_firewall_pricing | navigation | AWS WAF & Shield pricing section |
| navigate_ec2_pricing | navigation | Amazon EC2 pricing section |
| navigate_glue_pricing | navigation | AWS Glue pricing section |
| navigate_iot_pricing | navigation | AWS IoT Core pricing section |
| expected_firewall_content | assertion | AWS WAF pricing per web ACL |
| expected_ec2_content | assertion | On-Demand pricing per hour |
| expected_glue_content | assertion | ETL job pricing per DPU-Hour |
| expected_iot_content | assertion | Message pricing per million messages |
| min_products_count | count_min | 10 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key pricing sections missing or unavailable

**Iteration 1**  
*Expected error: Required pricing sections are not available or failed to load*

| Field | Type | Value |
|---|---|---|
| navigate_firewall_pricing | navigation | AWS WAF & Shield pricing section |
| navigate_ec2_pricing | navigation | Amazon EC2 pricing section |
| navigate_glue_pricing | navigation | AWS Glue pricing section |
| navigate_iot_pricing | navigation | AWS IoT Core pricing section |
| expected_firewall_content | assertion | `""` |
| expected_ec2_content | assertion | Service temporarily unavailable |
| expected_glue_content | assertion | `""` |
| expected_iot_content | assertion | `""` |
| min_products_count | count_min | 3 |

---

## TD-030: M03_BS_011 — Get started with AWS services for free

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_get_started_button | navigation | Get Started for Free |
| expected_url | url | https://aws.amazon.com/pricing/?nc2=h_pr_hub |
| verify_new_tab | assertion | new tab opened |
| verify_original_tab | assertion | original page remains open |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Button not found or navigation fails

**Iteration 1**  
*Expected error: Get Started for Free button not found*

| Field | Type | Value |
|---|---|---|
| click_get_started_button | navigation | `""` |
| expected_url | url | https://aws.amazon.com/pricing/?nc2=h_pr_hub |
| verify_new_tab | assertion | new tab opened |
| verify_original_tab | assertion | original page remains open |

#### NEG-002 (`boundary`) — Wrong redirect URL after click

**Iteration 1**  
*Expected error: Incorrect redirect URL - expected pricing page*

| Field | Type | Value |
|---|---|---|
| click_get_started_button | navigation | Get Started for Free |
| expected_url | url | https://aws.amazon.com/404 |
| verify_new_tab | assertion | new tab opened |
| verify_original_tab | assertion | original page remains open |

---

## TD-031: M03_BS_012 — Request customized pricing quote from AWS sales

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_pricing_quote_button | navigation | Request a Pricing quote |
| expected_url | url | https://aws.amazon.com/contact-us/sales-support-pricing/?ch=cta&cta=contact-sales |
| expected_page_heading | assertion | Contact AWS Sales |
| expected_contact_form | assertion | pricing quote request form |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation fails or lands on wrong page

**Iteration 1**  
*Expected error: Page not found or failed to load contact form*

| Field | Type | Value |
|---|---|---|
| click_pricing_quote_button | navigation | Request a Pricing quote |
| expected_url | url | https://aws.amazon.com/404 |
| expected_page_heading | assertion | `""` |
| expected_contact_form | assertion | `""` |

---

## TD-032: M01_BS_006 — Navigate through Products menu to find specific AWS services

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_products_menu | navigation | Products |
| expected_popup_menu | assertion | AWS products menu popup |
| locate_amazon_quick_card | assertion | Amazon Quick |
| click_amazon_quick | navigation | Amazon Quick service |
| expected_url | url | /amazon-quick |
| expected_service_heading | assertion | Amazon Quick |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Amazon Quick service not available or missing from menu

**Iteration 1**  
*Expected error: Amazon Quick service not found in products menu*

| Field | Type | Value |
|---|---|---|
| click_products_menu | navigation | Products |
| expected_popup_menu | assertion | AWS products menu popup |
| locate_amazon_quick_card | assertion | `""` |
| click_amazon_quick | navigation | Amazon Quick service |
| expected_url | url | /404 |
| expected_service_heading | assertion | Page Not Found |

---

## TD-033: M01_BS_007 — Browse homepage content as authenticated user

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| access_homepage_navigation | navigation | homepage navigation bar |
| browse_whats_new_section | assertion | What's New |
| view_client_images | assertion | image carousel |
| read_success_stories | assertion | customer success stories |
| min_carousel_images | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key homepage sections not loading or missing

**Iteration 1**  
*Expected error: What's New section failed to load*

| Field | Type | Value |
|---|---|---|
| access_homepage_navigation | navigation | homepage navigation bar |
| browse_whats_new_section | assertion | `""` |
| view_client_images | assertion | image carousel |
| read_success_stories | assertion | customer success stories |
| min_carousel_images | count_min | 3 |

---

## TD-034: M04_BS_001 — Navigate between different Partner sections using navigation bar

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_partner_header | navigation | Partner Solutions |
| expected_url_fragment | url | /partners/solutions |
| expected_section_heading | assertion | AWS Partner Solutions |
| expected_content_keyword | assertion | partner programs |
| min_navigation_items | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation fails or lands on wrong section

**Iteration 1**  
*Expected error: Page not found or navigation failed*

| Field | Type | Value |
|---|---|---|
| click_partner_header | navigation | Partner Solutions |
| expected_url_fragment | url | /404 |
| expected_section_heading | assertion | `""` |
| expected_content_keyword | assertion | partner programs |
| min_navigation_items | count_min | 3 |

---

## TD-035: M04_BS_002 — View AWS Partner Network getting started information

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | AWS Partner Network |
| expected_heading | assertion | Getting Started with AWS Partner Network |
| expected_guidance_content | assertion | Join the AWS Partner Network to grow your business |
| expected_next_steps | assertion | Apply now to become an AWS Partner |
| expected_url_fragment | url | /partners/partner-network |
| min_guidance_steps_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key partner network content missing or incorrect

**Iteration 1**  
*Expected error: Partner Network getting started section heading not found*

| Field | Type | Value |
|---|---|---|
| navigate_to_section | navigation | AWS Partner Network |
| expected_heading | assertion | `""` |
| expected_guidance_content | assertion | Join the AWS Partner Network to grow your business |
| expected_next_steps | assertion | Apply now to become an AWS Partner |
| expected_url_fragment | url | /partners/partner-network |
| min_guidance_steps_count | count_min | 3 |

---

## TD-036: M04_BS_003 — Explore AWS Partner benefits and expansion opportunities

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_to_section | navigation | Why become AWS Partner |
| expected_benefits_heading | assertion | Partner Benefits |
| expected_expansion_content | assertion | expansion opportunities |
| expected_value_proposition | assertion | value proposition |
| min_benefit_items | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Required section or content not available

**Iteration 1**  
*Expected error: Partner benefits section heading not found*

| Field | Type | Value |
|---|---|---|
| scroll_to_section | navigation | Why become AWS Partner |
| expected_benefits_heading | assertion | `""` |
| expected_expansion_content | assertion | expansion opportunities |
| expected_value_proposition | assertion | value proposition |
| min_benefit_items | count_min | 3 |

---

## TD-037: M04_BS_004 — Browse latest updates in What's New section

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | What's New |
| expected_heading | assertion | What's New |
| min_cards_count | count_min | 3 |
| expected_content_keyword | assertion | AWS Partner program |
| click_card_title | assertion | Latest Partner Program Updates |
| expected_detail_content | assertion | announcements |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — What's New section not available or empty

**Iteration 1**  
*Expected error: What's New section is not available or contains no updates*

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | What's New |
| expected_heading | assertion | `""` |
| min_cards_count | count_min | 0 |
| expected_content_keyword | assertion | AWS Partner program |
| click_card_title | assertion | Latest Partner Program Updates |
| expected_detail_content | assertion | announcements |

---

## TD-038: M04_BS_005 — Discover AWS Partner success stories and innovations

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_section_target | navigation | Partner Success with AWS |
| expected_success_stories | assertion | success stories from AWS Partners worldwide |
| expected_innovations_content | assertion | customer innovations driven by partners |
| expected_use_cases | assertion | partner use cases and achievements |
| min_partner_stories_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Missing or incorrect section content

**Iteration 1**  
*Expected error: Partner success stories content not found or failed to load*

| Field | Type | Value |
|---|---|---|
| navigate_section_target | navigation | Partner Success with AWS |
| expected_success_stories | assertion | `""` |
| expected_innovations_content | assertion | customer innovations driven by partners |
| expected_use_cases | assertion | partner use cases and achievements |
| min_partner_stories_count | count_min | 3 |

---

## TD-039: M04_BS_006 — Complete automated workflow execution for partner onboarding

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| execute_get_started_workflow | assertion | Get Started for Free workflow completed successfully |
| verify_workflow_status | assertion | Workflow executed without errors |
| execute_amazon_quick_search | assertion | Amazon Quick product search workflow completed |
| verify_second_workflow_status | assertion | Second workflow completed without errors |
| validate_all_steps_processed | assertion | All workflow steps successfully processed |
| expected_partner_page_url | url | /aws/partner/onboarding/complete |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Workflow execution failure or missing success indicators

**Iteration 1**  
*Expected error: Get Started workflow did not complete successfully*

| Field | Type | Value |
|---|---|---|
| execute_get_started_workflow | assertion | `""` |
| verify_workflow_status | assertion | Workflow executed without errors |
| execute_amazon_quick_search | assertion | Amazon Quick product search workflow completed |
| verify_second_workflow_status | assertion | Second workflow completed without errors |
| validate_all_steps_processed | assertion | All workflow steps successfully processed |
| expected_partner_page_url | url | /aws/partner/onboarding/complete |

---

## TD-040: M04_BS_007 — Execute comprehensive automated test suite for partner functionality

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| execute_test_case_one | assertion | Test Case 1: PASSED |
| execute_test_case_two | assertion | Test Case 2: PASSED |
| execute_test_case_three | assertion | Test Case 3: PASSED |
| execute_test_case_four | assertion | Test Case 4: PASSED |
| execute_test_case_five | assertion | Test Case 5: PASSED |
| verify_all_tests_status | assertion | All automated test cases completed successfully |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Test case execution failure

**Iteration 1**  
*Expected error: Automated test suite validation failed - not all test cases passed successfully*

| Field | Type | Value |
|---|---|---|
| execute_test_case_one | assertion | Test Case 1: FAILED |
| execute_test_case_two | assertion | Test Case 2: PASSED |
| execute_test_case_three | assertion | Test Case 3: PASSED |
| execute_test_case_four | assertion | Test Case 4: PASSED |
| execute_test_case_five | assertion | Test Case 5: PASSED |
| verify_all_tests_status | assertion | Test execution incomplete - 1 test case failed |

---

## TD-041: M04_BS_008 — Guest user initiates partner registration process

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | partner section |
| expected_partner_heading | assertion | AWS Partner Network |
| expected_signin_link | assertion | sign in to aws console |
| expected_redirect_url | url | https://signin.aws.amazon.com/signin |
| expected_partner_content | assertion | Join thousands of partners |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Required page elements missing or incorrect

**Iteration 1**  
*Expected error: Partner section heading not found on page*

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | partner section |
| expected_partner_heading | assertion | `""` |
| expected_signin_link | assertion | sign in to aws console |
| expected_redirect_url | url | https://signin.aws.amazon.com/signin |
| expected_partner_content | assertion | Join thousands of partners |

---

## TD-042: M04_BS_009 — Navigate partner collaboration workflow

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_work_with_partner | navigation | Work with an AWS Partner |
| expected_redirect_url | url | https://aws.amazon.com/partners/work-with-partners/ |
| click_become_partner | navigation | Become and AWS Partner |
| expected_return_page | assertion | AWS Partner page |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation links are broken or missing

**Iteration 1**  
*Expected error: Work with an AWS Partner link not found or not clickable*

| Field | Type | Value |
|---|---|---|
| click_work_with_partner | navigation | `""` |
| expected_redirect_url | url | https://aws.amazon.com/partners/work-with-partners/ |
| click_become_partner | navigation | Become and AWS Partner |
| expected_return_page | assertion | AWS Partner page |

---

## TD-043: M01_BS_008 — Browse homepage content as guest user

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_homepage_url | url | https://aws.amazon.com |
| expected_whats_new_section | assertion | What's New |
| expected_image_carousel | assertion | Image Carousel |
| expected_customer_stories | assertion | Customer Story Cards |
| scroll_navigation_bar | navigation | main navigation |
| min_content_sections_count | count_min | 3 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Key homepage sections missing or not visible

**Iteration 1**  
*Expected error: What's New section is not visible on homepage*

| Field | Type | Value |
|---|---|---|
| navigate_homepage_url | url | https://aws.amazon.com |
| expected_whats_new_section | assertion | `""` |
| expected_image_carousel | assertion | Image Carousel |
| expected_customer_stories | assertion | Customer Story Cards |
| scroll_navigation_bar | navigation | main navigation |
| min_content_sections_count | count_min | 3 |

---

## TD-044: M01_BS_009 — Access comprehensive AWS product information from homepage

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| browse_homepage_section | navigation | Products and Services |
| expected_product_heading | assertion | AWS Products |
| expected_service_description | assertion | Amazon Web Services offers reliable, scalable, and inexpensive cloud computing services |
| access_product_details | navigation | Compute Services |
| min_products_displayed | count_min | 5 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Expected content not found or missing

**Iteration 1**  
*Expected error: Product heading is not visible on homepage*

| Field | Type | Value |
|---|---|---|
| browse_homepage_section | navigation | Products and Services |
| expected_product_heading | assertion | `""` |
| expected_service_description | assertion | Amazon Web Services offers reliable, scalable, and inexpensive cloud computing services |
| access_product_details | navigation | Compute Services |
| min_products_displayed | count_min | 5 |

---

## TD-045: M01_BS_010 — Explore AWS service updates through What's New section

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_whats_new_section | navigation | What's New |
| expected_aws_updates_heading | assertion | What's New with AWS |
| expected_service_update_item | assertion | Amazon EC2 |
| min_update_items_count | count_min | 5 |
| select_feature_details | assertion | Learn more |
| expected_feature_description | assertion | AWS service features and capabilities |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — What's New section unavailable or empty

**Iteration 1**  
*Expected error: What's New section is currently unavailable or contains no updates*

| Field | Type | Value |
|---|---|---|
| navigate_whats_new_section | navigation | What's New |
| expected_aws_updates_heading | assertion | `""` |
| expected_service_update_item | assertion | `""` |
| min_update_items_count | count_min | 0 |
| select_feature_details | assertion | `""` |
| expected_feature_description | assertion | `""` |

---

## TD-046: M01_BS_011 — Navigate to Amazon QuickSight through Products menu

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_products_menu | navigation | Products |
| search_product_name | text | Amazon QuickSight |
| expected_service_heading | assertion | Amazon QuickSight |
| expected_url_fragment | url | /quicksight |
| expected_service_description | assertion | Business intelligence service |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Service not found or navigation fails

**Iteration 1**  
*Expected error: Service not found or page not available*

| Field | Type | Value |
|---|---|---|
| click_products_menu | navigation | Products |
| search_product_name | text | NonExistentService |
| expected_service_heading | assertion | `""` |
| expected_url_fragment | url | /404 |
| expected_service_description | assertion | `""` |

---
