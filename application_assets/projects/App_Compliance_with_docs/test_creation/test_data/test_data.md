# Test Data — App_Compliance_with_docs

Total: **11 dataset(s)**

---

## TD-001: GEN_BS_001 — Toggle Application Theme using Dark Mode Switch

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_toggle_switch | navigation | LOC-0001 |
| assert_active_theme | assertion | dark |
| assert_theme_class | assertion | theme-dark |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Theme toggle fails to update application visual theme to dark mode

**Iteration 1**  
*Expected error: Visual theme failed to switch to dark mode*

| Field | Type | Value |
|---|---|---|
| click_toggle_switch | navigation | LOC-0001 |
| assert_active_theme | assertion | light |
| assert_theme_class | assertion | theme-light |

---

## TD-002: GEN_BS_002 — Open Demo Project

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_demo_project_option | navigation | LOC-0002 |
| assert_demo_project_title | assertion | Demo Project |
| assert_demo_project_url | url | /projects/demo |
| assert_widgets_count | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Demo project content fails to load or returns missing project state

**Iteration 1**  
*Expected error: Unable to load demo project. Please try again later.*

| Field | Type | Value |
|---|---|---|
| click_demo_project_option | navigation | LOC-0002 |
| assert_demo_project_title | assertion | Project Not Found |
| assert_demo_project_url | url | /error/404 |
| assert_widgets_count | count_min | 0 |

---

## TD-003: GEN_BS_003 — Access BRD Compliance Criterion Level View

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_criterion_level_link | navigation | BRD Compliance Criterion Level (LOC-0003) |
| assert_criterion_heading | assertion | Criterion Level Compliance Overview |
| assert_url_path | url | /compliance/brd/criterion-level |
| assert_min_criteria_count | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Navigation target fails to load or displays 404 error

**Iteration 1**  
*Expected error: Failed to load BRD compliance criterion level view.*

| Field | Type | Value |
|---|---|---|
| click_criterion_level_link | navigation | BRD Compliance Criterion Level (LOC-0003) |
| assert_criterion_heading | assertion | 404 - Page Not Found |
| assert_url_path | url | /compliance/brd/error |
| assert_min_criteria_count | count_min | 0 |

---

## TD-004: GEN_BS_004 — Create a New Project

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| assert_heading | assertion | Create New Project |
| assert_url | url | /projects/new |
| assert_element | assertion | project_creation_modal |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Project creation workflow fails to launch upon clicking control

**Iteration 1**  
*Expected error: Failed to open project creation workflow*

| Field | Type | Value |
|---|---|---|
| assert_heading | assertion | Page Not Found |
| assert_url | url | /projects/error |
| assert_element | assertion | error_message_container |

---

## TD-005: M01_BS_001 — Switch Application Theme to Dark Mode

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_dark_mode_button | navigation | btn-dark-mode |
| assert_active_theme | assertion | dark |
| assert_theme_class | assertion | theme-dark |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Visual theme fails to switch to dark mode after clicking button

**Iteration 1**  
*Expected error: Visual theme failed to switch to dark mode*

| Field | Type | Value |
|---|---|---|
| click_dark_mode_button | navigation | btn-dark-mode |
| assert_active_theme | assertion | light |
| assert_theme_class | assertion | theme-light |

---

## TD-006: M01_BS_002 — Open Demo Project

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_open_demo_project_button | navigation | btn_open_demo_project |
| assert_demo_project_title | assertion | Demo Project |
| assert_demo_project_url | url | /projects/demo |
| assert_project_widgets_count | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Demo project content fails to load or returns missing project state

**Iteration 1**  
*Expected error: Unable to load demo project. Please try again later.*

| Field | Type | Value |
|---|---|---|
| click_open_demo_project_button | navigation | btn_open_demo_project |
| assert_demo_project_title | assertion | Project Not Found |
| assert_demo_project_url | url | /error/404 |
| assert_project_widgets_count | count_min | 0 |

---

## TD-007: M01_BS_003 — Access BRD Compliance Criterion Level View

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_brd_criterion_button | navigation | LOC-BRD-001 |
| assert_criterion_view_title | assertion | BRD Compliance Criterion Level View |
| assert_criterion_url | url | /compliance/brd/criterion-level |
| assert_criterion_details_count | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — BRD compliance criterion level view fails to load or returns missing content state

**Iteration 1**  
*Expected error: Unable to load BRD compliance criterion level view. Content unavailable.*

| Field | Type | Value |
|---|---|---|
| click_brd_criterion_button | navigation | LOC-BRD-001 |
| assert_criterion_view_title | assertion | Page Not Found |
| assert_criterion_url | url | /error/404 |
| assert_criterion_details_count | count_min | 0 |

---

## TD-008: M01_BS_004 — Create New Project

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_new_project_button | navigation | LOC-0004 |
| assert_project_creation_title | assertion | Create New Project |
| assert_project_creation_url | url | /projects/new |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Project creation workflow fails to initiate or screen fails to load

**Iteration 1**  
*Expected error: Unable to initiate new project workflow. Please try again later.*

| Field | Type | Value |
|---|---|---|
| click_new_project_button | navigation | LOC-0004 |
| assert_project_creation_title | assertion | Service Unavailable |
| assert_project_creation_url | url | /error/500 |

---

## TD-009: M01_BS_005 — Delete Item or Resource

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_delete_button | navigation | LOC-0005 |
| click_confirm_button | navigation | LOC-0006 |
| assert_success_message | assertion | Item successfully deleted |
| assert_deleted_item_status | assertion | Removed |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Item deletion fails due to dependency constraints or system failure

**Iteration 1**  
*Expected error: Unable to delete item. It may be in use or referenced by another resource.*

| Field | Type | Value |
|---|---|---|
| click_delete_button | navigation | LOC-0005 |
| click_confirm_button | navigation | LOC-0006 |
| assert_success_message | assertion | Failed to delete item |
| assert_deleted_item_status | assertion | Active |

---

## TD-010: M01_BS_006 — Access Shopflow Demo

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_shopflow_demo_option | navigation | LOC-0006 |
| assert_shopflow_demo_title | assertion | Shopflow Demo |
| assert_shopflow_demo_url | url | /demo/shopflow |
| assert_demo_components_count | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Shopflow demo project content fails to load or returns error state

**Iteration 1**  
*Expected error: Unable to load Shopflow demo project. Please try again later.*

| Field | Type | Value |
|---|---|---|
| click_shopflow_demo_option | navigation | LOC-0006 |
| assert_shopflow_demo_title | assertion | Project Not Found |
| assert_shopflow_demo_url | url | /error/404 |
| assert_demo_components_count | count_min | 0 |

---

## TD-011: M01_BS_007 — Execute Open Action

**Actor:** User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_document_item | select | DOC-2024-Compliance-Report.pdf |
| click_open_action | navigation | LOC-0007 |
| assert_document_title | assertion | DOC-2024-Compliance-Report.pdf |
| assert_view_rendered | assertion | Document Viewer Loaded |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Target document is unavailable or unreadable upon open action

**Iteration 1**  
*Expected error: Unable to open the selected resource. The document format is invalid or corrupted.*

| Field | Type | Value |
|---|---|---|
| select_document_item | select | DOC-CORRUPTED-000.pdf |
| click_open_action | navigation | LOC-0007 |
| assert_document_title | assertion | Error Loading Resource |
| assert_view_rendered | assertion | Failed to render document |

#### NEG-002 (`boundary`) — Opening a document with maximum allowed title length

**Iteration 1**

| Field | Type | Value |
|---|---|---|
| select_document_item | select | DOC_2024_A_Very_Long_Resource_Name_That_Reaches_The_Maximum_Allowed_Character_Limit_For_Document_Titles_In_System_Archive_Folder_Final_Version_Verified.pdf |
| click_open_action | navigation | LOC-0007 |
| assert_document_title | assertion | DOC_2024_A_Very_Long_Resource_Name_That_Reaches_The_Maximum_Allowed_Character_Limit_For_Document_Titles_In_System_Archive_Folder_Final_Version_Verified.pdf |
| assert_view_rendered | assertion | Document Viewer Loaded |

---
