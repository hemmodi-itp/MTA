# Test Data — AWS_WORLD

Total: **5 dataset(s)**

---

## TD-001: M01_BS_001 — Navigate to page information using navigation bar

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_navigation_item | navigation | About Us |
| expected_page_heading | assertion | About AWS World |
| expected_url_fragment | url | /about |
| expected_page_content | assertion | Learn more about our mission and values |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation item leads to missing or broken page

**Iteration 1**  
*Expected error: Page content failed to load*

| Field | Type | Value |
|---|---|---|
| click_navigation_item | navigation | About Us |
| expected_page_heading | assertion | `""` |
| expected_url_fragment | url | /about |
| expected_page_content | assertion | `""` |

---

## TD-002: M01_BS_002 — Browse new AWS items in What's New section

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_whats_new_section | navigation | What's New |
| expected_section_heading | assertion | What's New with AWS |
| min_aws_items_count | count_min | 5 |
| select_aws_item | assertion | Amazon EC2 Instance Types Update |
| expected_item_details | assertion | Learn about the latest EC2 instance capabilities |
| expected_url_fragment | url | /whats-new/ec2-instance-update |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — What's New section missing or empty

**Iteration 1**  
*Expected error: What's New section is currently unavailable*

| Field | Type | Value |
|---|---|---|
| navigate_whats_new_section | navigation | What's New |
| expected_section_heading | assertion | `""` |
| min_aws_items_count | count_min | 0 |
| select_aws_item | assertion | `""` |
| expected_item_details | assertion | `""` |
| expected_url_fragment | url | /error/404 |

---

## TD-003: M01_BS_003 — View client showcase through image carousel

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| view_carousel_section | navigation | client-showcase-carousel |
| expected_carousel_heading | assertion | Our Client Success Stories |
| min_client_images_count | count_min | 3 |
| click_client_image | navigation | first-client-image |
| expected_client_details | assertion | Client Details |
| expected_detail_url | url | /client-showcase/details |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Carousel content fails to load or display

**Iteration 1**  
*Expected error: Carousel content unavailable*

| Field | Type | Value |
|---|---|---|
| view_carousel_section | navigation | client-showcase-carousel |
| expected_carousel_heading | assertion | `""` |
| min_client_images_count | count_min | 0 |
| click_client_image | navigation | first-client-image |
| expected_client_details | assertion | `""` |
| expected_detail_url | url | /404 |

---

## TD-004: M01_BS_004 — Read customer success stories through story cards

**Actor:** Logged In User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | Customer Story Cards |
| expected_story_cards | assertion | customer success stories |
| min_story_count | count_min | 3 |
| click_story_card | navigation | story card link |
| expected_full_story | assertion | detailed customer story content |
| expected_story_url | url | /customer-stories/ |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Customer Story Cards section not populated or missing

**Iteration 1**  
*Expected error: No customer stories are currently available*

| Field | Type | Value |
|---|---|---|
| scroll_target_section | navigation | Customer Story Cards |
| expected_story_cards | assertion | `""` |
| min_story_count | count_min | 0 |
| click_story_card | navigation | story card link |
| expected_full_story | assertion | No stories available |
| expected_story_url | url | /customer-stories/ |

---

## TD-005: M01_BS_005 — Explore AWS products information from homepage

**Actor:** Guest user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_homepage_section | navigation | AWS Products |
| expected_products_heading | assertion | AWS Products & Services |
| expected_product_categories | assertion | Compute, Storage, Database, Machine Learning, Analytics |
| select_product_detail | navigation | Amazon EC2 |
| expected_product_description | assertion | Scalable computing capacity in the Amazon Web Services (AWS) cloud |
| min_product_items_count | count_min | 10 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Missing or incorrect product information sections

**Iteration 1**  
*Expected error: Products section heading not found or not visible*

| Field | Type | Value |
|---|---|---|
| navigate_homepage_section | navigation | AWS Products |
| expected_products_heading | assertion | `""` |
| expected_product_categories | assertion | Compute, Storage, Database, Machine Learning, Analytics |
| select_product_detail | navigation | Amazon EC2 |
| expected_product_description | assertion | Scalable computing capacity in the Amazon Web Services (AWS) cloud |
| min_product_items_count | count_min | 10 |

---
