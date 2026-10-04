# Test Data — Blog_Writing_Agent

Total: **5 dataset(s)**

---

## TD-001: M01_BS_001 — Navigate to Main Menu

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_main_menu_element | navigation | LOC-0004 |
| assert_menu_container | assertion | Main Menu |
| assert_navigation_options | assertion | Navigation Options |
| assert_min_menu_items | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Main menu interface fails to open or present navigation options

**Iteration 1**  
*Expected error: Main menu interface failed to open or render navigation options.*

| Field | Type | Value |
|---|---|---|
| click_main_menu_element | navigation | LOC-0004 |
| assert_menu_container | assertion | `""` |
| assert_navigation_options | assertion | Menu Unavailable |
| assert_min_menu_items | count_min | 0 |

---

## TD-002: M01_BS_002 — Deploy Blog Agent Service

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| target_deploy_button | navigation | LOC-0003 |
| expected_heading | assertion | Blog Agent Service |
| expected_status_message | assertion | Deployment process successfully initiated |
| expected_redirect_url | url | /control-panel/deployments/blog-agent/status |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Deployment process fails to initiate due to service error

**Iteration 1**  
*Expected error: Unable to trigger deployment for blog agent service*

| Field | Type | Value |
|---|---|---|
| target_deploy_button | navigation | LOC-0003 |
| expected_heading | assertion | Blog Agent Service |
| expected_status_message | assertion | Failed to initiate deployment process |
| expected_redirect_url | url | /control-panel/deployments/blog-agent/error |

---

## TD-003: M01_BS_003 — Stop Active Process

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_stop_target | navigation | LOC-0002 |
| assert_process_status | assertion | Terminated |
| assert_termination_message | assertion | Process execution halted successfully. |
| count_min_running_processes | count_min | 0 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Process fails to terminate and remains in active state

**Iteration 1**  
*Expected error: Process execution could not be terminated.*

| Field | Type | Value |
|---|---|---|
| click_stop_target | navigation | LOC-0002 |
| assert_process_status | assertion | Running |
| assert_termination_message | assertion | Unable to stop execution. |
| count_min_running_processes | count_min | 1 |

---

## TD-004: M01_BS_004 — Jump to Section Heading

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_section_anchor | navigation | #key-features |
| assert_heading_text | assertion | Key Features |
| assert_target_url | url | https://blog.example.com/posts/guide-to-automation#key-features |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Target section anchor is broken or target heading element is missing from the document

**Iteration 1**  
*Expected error: Element matching target heading anchor not found in DOM*

| Field | Type | Value |
|---|---|---|
| select_section_anchor | navigation | #non-existent-heading |
| assert_heading_text | assertion | Key Features |
| assert_target_url | url | https://blog.example.com/posts/guide-to-automation#non-existent-heading |

---

## TD-005: M01_BS_005 — Interact with Generic UI Element

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_target_selector | navigation | LOC-0001 |
| assert_element_presence | assertion | Element LOC-0001 is displayed |
| assert_ui_event_triggered | assertion | Element event triggered successfully |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Target interactive element is missing from the active page

**Iteration 1**  
*Expected error: Element with selector LOC-0001_MISSING not found*

| Field | Type | Value |
|---|---|---|
| navigate_target_selector | navigation | LOC-0001_MISSING |
| assert_element_presence | assertion | Element LOC-0001_MISSING is displayed |
| assert_ui_event_triggered | assertion | Element event triggered successfully |

---
