# Business Scenarios — AWS_Test

Total: **46 scenario(s)**

---

## M01_BS_001: Navigate using navigation bar to fetch page information

**Business Objective:** Enable users to quickly access page information through direct navigation
**Actor:** Guest user
**Confidence:** 80%

**Preconditions:**
- User is on the AWS homepage
- Navigation bar is visible and accessible

**Steps:**
1. User clicks on navigation bar element
2. System fetches information about the selected page
3. System displays the requested page information

**Expected Result:** User receives direct access to the requested page information through the navigation bar

**Traceability:**
- File: module_01_homePage.md | Req: REQ-001 | Section: 2. Page / Feature Overview

---

## M01_BS_002: Browse new AWS items in What's New section

**Business Objective:** Keep users informed about latest AWS offerings and updates
**Actor:** Logged In User
**Confidence:** 85%

**Preconditions:**
- User is on the AWS homepage
- What's New section is displayed
- New AWS items are available

**Steps:**
1. User navigates to What's New section
2. User browses through the displayed new items
3. User clicks on a specific new item to view details

**Expected Result:** User can view and access all new items available on AWS through the What's New section

**Traceability:**
- File: module_01_homePage.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M01_BS_003: View client images through image carousel

**Business Objective:** Showcase AWS client relationships and build credibility through visual representation
**Actor:** Guest user
**Confidence:** 82%

**Preconditions:**
- User is on the AWS homepage
- Image carousel is loaded with client images
- Client images are available for display

**Steps:**
1. User views the image carousel on the homepage
2. User navigates through carousel images using navigation controls
3. User views images of specific AWS clients

**Expected Result:** User can view and navigate through images displaying specific AWS clients in the carousel

**Traceability:**
- File: module_01_homePage.md | Req: REQ-003 | Section: 2. Page / Feature Overview

---

## M01_BS_004: Browse customer success stories through story cards

**Business Objective:** Demonstrate AWS value through customer testimonials and success cases
**Actor:** Logged In User
**Confidence:** 85%

**Preconditions:**
- User is on the AWS homepage
- Customer Story Cards section is visible
- Customer stories and cards are loaded

**Steps:**
1. User scrolls to Customer Story Cards section
2. User browses through available customer story cards
3. User clicks on a specific customer story card to read details

**Expected Result:** User can access and read customer stories through the interactive story cards interface

**Traceability:**
- File: module_01_homePage.md | Req: REQ-004 | Section: 2. Page / Feature Overview

---

## M01_BS_005: Return to top of page using back to top functionality

**Business Objective:** Improve user navigation experience by providing quick access to page header
**Actor:** Guest user
**Confidence:** 95%

**Preconditions:**
- User has scrolled down on the AWS homepage
- Back to top button is visible
- User is at a lower position on the page

**Steps:**
1. User scrolls down to the bottom of the page
2. User locates the back to top button
3. User clicks on the back to top button

**Expected Result:** User is immediately taken to the top of the page

**Traceability:**
- File: module_01_homePage.md | Req: REQ-005 | Section: 5. User Workflows

---

## M01_BS_006: Navigate through Products menu to find specific AWS services

**Business Objective:** Enable users to efficiently discover and access specific AWS products through organized navigation
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the AWS homepage
- Navigation bar is visible and functional
- Products menu contains Amazon Quick service

**Steps:**
1. Click on products in the navigation bar
2. Review the opened pop-up menu with available products
3. Locate the card with Amazon Quick service
4. Click on Amazon Quick to access the service

**Expected Result:** User is redirected to the Amazon Quick service page or section

**Traceability:**
- File: module_01_homePage.md | Req: REQ-001 | Section: 2. Page / Feature Overview

---

## M01_BS_007: Browse homepage content as authenticated user

**Business Objective:** Provide personalized homepage experience for authenticated users with full access to all homepage features
**Actor:** Logged In User
**Confidence:** 90%

**Preconditions:**
- User has valid login credentials
- User is successfully logged into the AWS platform
- Homepage is fully loaded with all sections

**Steps:**
1. Access the homepage navigation bar
2. Browse through the 'What's New' section to review latest AWS updates
3. View client images in the image carousel
4. Read customer success stories in the story cards section

**Expected Result:** Logged in user can access and interact with all homepage sections and features

**Traceability:**
- File: module_01_homePage.md | Req: REQ-001 | Section: 2. Page / Feature Overview
- File: module_01_homePage.md | Req: REQ-002 | Section: 2. Page / Feature Overview
- File: module_01_homePage.md | Req: REQ-003 | Section: 2. Page / Feature Overview
- File: module_01_homePage.md | Req: REQ-004 | Section: 2. Page / Feature Overview

---

## M01_BS_008: Browse homepage content as guest user

**Business Objective:** Enable non-authenticated users to access and explore AWS homepage content to understand available services and information
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is not logged in to AWS
- AWS homepage is accessible

**Steps:**
1. Navigate to AWS homepage
2. Browse through available sections including What's New, Image Carousel, and Customer Story Cards
3. Use navigation bar to access different page information
4. View content without authentication requirements

**Expected Result:** Guest user can successfully view and browse all public homepage content without requiring login credentials

**Traceability:**
- File: module_01_homePage.md | Req: REQ-001 | Section: Page / Feature Overview
- File: module_01_homePage.md | Req: REQ-002 | Section: Page / Feature Overview
- File: module_01_homePage.md | Req: REQ-003 | Section: Page / Feature Overview
- File: module_01_homePage.md | Req: REQ-004 | Section: Page / Feature Overview

---

## M01_BS_009: Access comprehensive AWS product information from homepage

**Business Objective:** Enable users to discover and learn about AWS products and services through the homepage
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the AWS homepage
- AWS products information is available

**Steps:**
1. Browse through the homepage sections
2. Review available AWS product information
3. Access detailed product descriptions and features

**Expected Result:** User successfully obtains information about AWS products available on the platform

**Traceability:**
- File: module_01_homePage.md | Req: REQ-005 | Section: 1. Purpose

---

## M01_BS_010: Explore AWS service updates through What's New section

**Business Objective:** Keep users informed about latest AWS features and service updates
**Actor:** Logged In User
**Confidence:** 90%

**Preconditions:**
- User is authenticated and on the homepage
- What's New section contains current AWS updates

**Steps:**
1. Navigate to the What's New section
2. Browse through the list of new AWS items
3. Select specific new features for detailed information

**Expected Result:** User is informed about the latest AWS services and features available

**Traceability:**
- File: module_01_homePage.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M01_BS_011: Navigate to Amazon QuickSight through Products menu

**Business Objective:** Enable users to discover and access specific AWS services efficiently
**Actor:** Guest user
**Confidence:** 80%

**Preconditions:**
- User is on the AWS homepage
- Products menu is accessible
- Amazon QuickSight is listed in the products

**Steps:**
1. Click on the Products menu item
2. Search for Amazon QuickSight in the product listing
3. Select Amazon QuickSight from the available options

**Expected Result:** User successfully navigates to Amazon QuickSight service page

**Traceability:**
- File: module_01_homePage.md | Req: REQ-001 | Section: 2. Page / Feature Overview

---

## M02_BS_001: User navigates Aurora page using navigation bar

**Business Objective:** Enable users to quickly access page information through direct navigation
**Actor:** Guest user
**Confidence:** 90%

**Preconditions:**
- User is on the Aurora page
- Navigation bar is visible and functional

**Steps:**
1. User views the navigation bar on the Aurora page
2. User clicks on navigation elements to fetch page information directly

**Expected Result:** User successfully retrieves information about the page through the navigation bar

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-001 | Section: 2. Page / Feature Overview

---

## M02_BS_002: User reads Aurora introduction information

**Business Objective:** Provide users with comprehensive understanding of what Aurora is
**Actor:** Guest user
**Confidence:** 90%

**Preconditions:**
- User is on the Aurora page
- What is Aurora section is visible on the page

**Steps:**
1. User scrolls to the 'What is Aurora' section
2. User reads the description about Aurora

**Expected Result:** User gains understanding of Aurora through the descriptive content

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M02_BS_003: User explores Aurora benefits information

**Business Objective:** Educate users about the advantages and value proposition of Aurora
**Actor:** Logged In User
**Confidence:** 90%

**Preconditions:**
- User is on the Aurora page
- Benefits of Aurora section is available on the page

**Steps:**
1. User navigates to the 'Benefits of Aurora' section
2. User reviews the listed benefits of Aurora

**Expected Result:** User understands the key benefits and advantages of using Aurora

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-003 | Section: 2. Page / Feature Overview

---

## M02_BS_004: User views customer success stories

**Business Objective:** Provide social proof and real-world examples of Aurora success through customer testimonials
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the Aurora page
- Customer Story Cards section is displayed on the page

**Steps:**
1. User scrolls to the Customer Story Cards section
2. User browses through the customer stories
3. User clicks on individual story cards to read detailed testimonials

**Expected Result:** User views customer success stories and testimonials about Aurora

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-004 | Section: 2. Page / Feature Overview

---

## M02_BS_005: User follows Get Started with Aurora workflow

**Business Objective:** Guide users to Aurora resources and documentation for implementation
**Actor:** Logged In User
**Confidence:** 95%

**Preconditions:**
- User is on the Aurora page
- Get Started with Aurora button is visible and functional

**Steps:**
1. User clicks on 'Get Started with Aurora'
2. System redirects user to https://aws.amazon.com/rds/aurora/resources/
3. User scrolls down to find the search field
4. User searches for 'User Guide'
5. User clicks on the User Guide card

**Expected Result:** User successfully navigates to Aurora User Guide through the guided workflow

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-005 | Section: 8. Acceptance Criteria

---

## M02_BS_006: User explores Aurora pricing information

**Business Objective:** Provide detailed pricing information and feature costs to help users make informed decisions
**Actor:** Guest user
**Confidence:** 95%

**Preconditions:**
- User is on the Aurora page
- Pricing section is accessible

**Steps:**
1. User clicks on Pricing
2. User scrolls down to find pricing information
3. User locates the 'Additional features and costs' section
4. User clicks the + sign to expand all 16 sections
5. User reviews the expanded pricing details
6. User clicks the - sign to collapse all 16 sections

**Expected Result:** User successfully views and manages the display of detailed Aurora pricing information

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-005 | Section: 8. Acceptance Criteria

---

## M02_BS_007: Guest user explores Aurora product features

**Business Objective:** Allow potential customers to discover and explore AWS Aurora features without requiring authentication
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User has access to the Aurora product page
- User is not logged into any AWS account

**Steps:**
1. Navigate to the Aurora product page
2. Browse through the product showcase sections
3. Review Aurora feature descriptions and capabilities
4. Explore available product information

**Expected Result:** Guest user successfully views and explores Aurora features through the product showcase

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-001 | Section: 1. Purpose

---

## M02_BS_008: Logged in user accesses Aurora product information

**Business Objective:** Provide authenticated users with comprehensive Aurora product information and features
**Actor:** Logged In User
**Confidence:** 90%

**Preconditions:**
- User has valid login credentials
- User is successfully logged into the system
- Aurora product page is accessible

**Steps:**
1. Access the Aurora product page while logged in
2. Use navigation bar to explore different page sections
3. Review Aurora description and benefits sections
4. Browse customer story cards

**Expected Result:** Logged in user successfully accesses all Aurora product information sections with full navigation capabilities

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-001 | Section: 1. Purpose
- File: module_02_Aurora.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M02_BS_009: User executes automated workflows successfully

**Business Objective:** Ensure all defined user workflows function correctly through automated execution
**Actor:** Logged In User
**Confidence:** 95%

**Preconditions:**
- All automated workflows are configured and available
- User has access to Aurora page functionalities
- System automation capabilities are enabled

**Steps:**
1. Initiate execution of the Get Started with Aurora workflow
2. Verify successful completion of first workflow
3. Execute the Pricing exploration workflow
4. Confirm successful completion of second workflow

**Expected Result:** Both automated workflows execute successfully without errors

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-006 | Section: 8. Acceptance Criteria

---

## M02_BS_010: System executes all automated test cases

**Business Objective:** Validate system functionality through comprehensive automated testing
**Actor:** Guest user
**Confidence:** 95%

**Preconditions:**
- All five test cases are configured and available
- Automated testing framework is operational
- Aurora page components are accessible

**Steps:**
1. Execute first automated test case
2. Execute second automated test case
3. Execute third automated test case
4. Execute fourth automated test case
5. Execute fifth automated test case
6. Verify all test results

**Expected Result:** All five automated test cases execute successfully and pass validation criteria

**Traceability:**
- File: module_02_Aurora.md | Req: REQ-007 | Section: 8. Acceptance Criteria

---

## M03_BS_007: Browse AWS Aurora pricing page with navigation to different pricing models

**Business Objective:** Allow users to view AWS Aurora pricing information and navigate between different pricing models
**Actor:** Guest user
**Confidence:** 90%

**Preconditions:**
- User is on the AWS Aurora pricing page
- Page has loaded completely with navigation bar visible

**Steps:**
1. View the AWS Aurora pricing product showcase
2. Locate the navigation bar for pricing models
3. Navigate to different pricing models using the navigation bar
4. Verify pricing information is displayed for each model

**Expected Result:** User can successfully view AWS Aurora pricing and navigate between different pricing models using the navigation bar

**Business Rules:** BR-001

**Traceability:**
- File: module_03_Pricing.md | Req: REQ-001 | Section: 2. Page / Feature Overview

---

## M03_BS_008: Access Understand Pricing section to learn how to get started

**Business Objective:** Provide users with guidance on how to get started with AWS pricing
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the AWS pricing page
- Understand Pricing section is visible on the page

**Steps:**
1. Navigate to the Understand Pricing section
2. Review the how to get started information
3. Verify all getting started guidance is clearly displayed

**Expected Result:** User can access and understand the getting started information in the Understand Pricing section

**Business Rules:** BR-001

**Traceability:**
- File: module_03_Pricing.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M03_BS_009: Review payment options in How to Pay section

**Business Objective:** Enable users to understand available payment methods for AWS services
**Actor:** Logged In User
**Confidence:** 85%

**Preconditions:**
- User is on the AWS pricing page
- How to Pay section is accessible on the page

**Steps:**
1. Navigate to the How to Pay section
2. Review the different modes of payment available
3. Verify all payment options are clearly listed and described

**Expected Result:** User can view and understand all available payment methods in the How to Pay section

**Business Rules:** BR-001

**Traceability:**
- File: module_03_Pricing.md | Req: REQ-003 | Section: 2. Page / Feature Overview

---

## M03_BS_010: Browse pricing information for multiple AWS products

**Business Objective:** Allow users to compare pricing across different AWS services including firewall, EC2, Glue job, and IoT
**Actor:** Guest user
**Confidence:** 90%

**Preconditions:**
- User is on the AWS pricing page
- Product pricing sections are loaded and visible

**Steps:**
1. Navigate to the firewall pricing section
2. Review EC2 pricing information
3. Check Glue job pricing details
4. Browse IoT service pricing
5. View pricing for at least 6 additional AWS products from the available options

**Expected Result:** User can successfully view pricing information for firewall, EC2, Glue job, IoT, and at least 10 AWS products total

**Business Rules:** BR-001

**Traceability:**
- File: module_03_Pricing.md | Req: REQ-004 | Section: 2. Page / Feature Overview

---

## M03_BS_011: Get started with AWS services for free

**Business Objective:** Enable users to access AWS free tier offerings through dedicated link
**Actor:** Guest user
**Confidence:** 95%

**Preconditions:**
- User is on the AWS pricing page
- Get Started for Free button is visible and clickable

**Steps:**
1. Locate the Get Started for Free button
2. Click on the Get Started for Free button
3. Verify redirection to https://aws.amazon.com/pricing/?nc2=h_pr_hub in a new tab
4. Confirm the original page remains open in the previous tab

**Expected Result:** User is redirected to the AWS pricing hub in a new tab while maintaining access to the original page

**Business Rules:** BR-001

**Traceability:**
- File: module_03_Pricing.md | Req: REQ-005 | Section: 5. User Workflows

---

## M03_BS_012: Request customized pricing quote from AWS sales

**Business Objective:** Enable users to contact AWS sales team for personalized pricing information
**Actor:** Logged In User
**Confidence:** 95%

**Preconditions:**
- User is on the AWS pricing page
- Request a Pricing quote button is visible and clickable

**Steps:**
1. Locate the Request a Pricing quote button
2. Click on the Request a Pricing quote button
3. Verify redirection to https://aws.amazon.com/contact-us/sales-support-pricing/?ch=cta&cta=contact-sales in the same tab
4. Confirm the page loads successfully with contact form

**Expected Result:** User is redirected to the AWS sales contact page in the same tab and can access the pricing quote request form

**Business Rules:** BR-001

**Traceability:**
- File: module_03_Pricing.md | Req: REQ-006 | Section: 5. User Workflows

---

## M04_BS_001: Navigate between different Partner sections using navigation bar

**Business Objective:** Enable users to easily move between different Partner-related sections and pages
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the AWS Partners page
- Navigation bar with Partner headers is visible

**Steps:**
1. User views the navigation bar with different Partner Navigation headers
2. User clicks on a different Partner Navigation header
3. System migrates user to the selected Partner section

**Expected Result:** User is successfully navigated to the selected Partner section with appropriate content displayed

**Traceability:**
- File: module_04_Partners.md | Req: REQ-001 | Section: 2. Page / Feature Overview

---

## M04_BS_002: View AWS Partner Network getting started information

**Business Objective:** Provide clear guidance to potential partners on how to begin their AWS partnership journey
**Actor:** Guest user
**Confidence:** 90%

**Preconditions:**
- User is on the AWS Partners page
- AWS Partner Network section is available

**Steps:**
1. User navigates to the AWS Partner Network section
2. User views the getting started information
3. User reads through the provided guidance and steps

**Expected Result:** User understands how to get started as an AWS Partner with clear next steps displayed

**Traceability:**
- File: module_04_Partners.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M04_BS_003: Explore AWS Partner benefits and expansion opportunities

**Business Objective:** Educate potential partners about the value proposition and growth opportunities of becoming an AWS Partner
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the AWS Partners page
- Why become AWS Partner section is visible

**Steps:**
1. User scrolls to the 'Why become AWS Partner' section
2. User reviews the different benefits displayed
3. User examines partner expansion opportunities
4. User considers the value proposition presented

**Expected Result:** User has comprehensive understanding of AWS Partner benefits and expansion potential

**Traceability:**
- File: module_04_Partners.md | Req: REQ-003 | Section: 2. Page / Feature Overview

---

## M04_BS_004: Browse latest updates in What's New section

**Business Objective:** Keep partners and potential partners informed about recent AWS Partner program updates and announcements
**Actor:** Logged In User
**Confidence:** 90%

**Preconditions:**
- User is on the AWS Partners page
- What's New section with cards is displayed

**Steps:**
1. User locates the 'What's New' section
2. User browses through the displayed cards
3. User clicks on cards of interest to view more details
4. User reads the latest updates and announcements

**Expected Result:** User is informed about the latest AWS Partner program updates and can access detailed information

**Traceability:**
- File: module_04_Partners.md | Req: REQ-004 | Section: 2. Page / Feature Overview

---

## M04_BS_005: Discover AWS Partner success stories and innovations

**Business Objective:** Showcase real-world examples of partner success to inspire and demonstrate the value of AWS partnerships
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- User is on the AWS Partners page
- Partner Success with AWS section is available

**Steps:**
1. User navigates to the 'Partner Success with AWS' section
2. User browses through success stories from AWS Partners worldwide
3. User reads about customer innovations driven by partners
4. User explores different partner use cases and achievements

**Expected Result:** User gains insights into how AWS Partners drive innovation and achieve success with their customers

**Traceability:**
- File: module_04_Partners.md | Req: REQ-005 | Section: 2. Page / Feature Overview

---

## M04_BS_006: Complete automated workflow execution for partner onboarding

**Business Objective:** Ensure both partner workflows are fully automated and function correctly for seamless partner experience
**Actor:** Logged In User
**Confidence:** 90%

**Preconditions:**
- User has valid login credentials
- AWS Partner page is accessible
- Automated workflow system is operational

**Steps:**
1. Execute 'get Started for Free' workflow automatically
2. Verify workflow completes without errors
3. Execute 'User looks for Amazon Quick in Products' workflow automatically
4. Verify second workflow completes without errors
5. Validate both workflows have successfully processed all steps

**Expected Result:** Both partner workflows are executed automatically and complete successfully with all steps verified

**Traceability:**
- File: module_04_Partners.md | Req: REQ-006 | Section: 8. Acceptance Criteria

---

## M04_BS_007: Execute comprehensive automated test suite for partner functionality

**Business Objective:** Validate all partner page features through automated testing to ensure quality and reliability
**Actor:** Guest user
**Confidence:** 85%

**Preconditions:**
- AWS Partner page is loaded and accessible
- All five test cases are defined and ready for execution
- Test automation framework is operational

**Steps:**
1. Execute first automated test case
2. Execute second automated test case
3. Execute third automated test case
4. Execute fourth automated test case
5. Execute fifth automated test case
6. Verify all test cases completed successfully

**Expected Result:** All five automated test cases execute successfully and pass validation criteria

**Traceability:**
- File: module_04_Partners.md | Req: REQ-007 | Section: 8. Acceptance Criteria

---

## M04_BS_008: Guest user initiates partner registration process

**Business Objective:** Allow prospective partners to begin AWS partnership enrollment without requiring prior authentication
**Actor:** Guest user
**Confidence:** 80%

**Preconditions:**
- User is on AWS Partner page
- User is not logged in
- Partner registration functionality is available

**Steps:**
1. Click on 'Become an AWS Partner' button
2. Verify page redirects to same page and scrolls to partner section
3. Click on 'sign in to aws console' link
4. Confirm redirection to login page at https://signin.aws.amazon.com/signin

**Expected Result:** Guest user is successfully guided through partner registration flow and redirected to AWS login page

**Traceability:**
- File: module_04_Partners.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## M04_BS_009: Navigate partner collaboration workflow

**Business Objective:** Enable users to explore existing partner collaboration options and return to partnership opportunities
**Actor:** Guest user
**Confidence:** 80%

**Preconditions:**
- User is on AWS Partner page
- Partner collaboration links are functional

**Steps:**
1. Click on 'Work with an AWS Partner' option
2. Verify redirection to https://aws.amazon.com/partners/work-with-partners/ in same tab
3. Click on 'Become and AWS Partner' link
4. Confirm user is taken back to the original AWS Partner page

**Expected Result:** User successfully navigates partner collaboration workflow and returns to main partner page

**Traceability:**
- File: module_04_Partners.md | Req: REQ-002 | Section: 2. Page / Feature Overview

---

## SC-001: Save Changes

**Business Objective:** Allow user to save changes on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Enter element in the input field
2. Enter allow crosscontext behavioral ads in the input field
3. Enter opt out of crosscontext behavioral ads in the input field
4. Enter im looking for in the input field
5. Enter search in the input field
6. Click the save preferences

**Expected Result:** save_preferences_opened

---

## SC-002: User Login

**Business Objective:** Allow user to user login on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the sign in to console

**Expected Result:** sign_in_to_console_opened

---

## SC-003: Create Account

**Business Objective:** Allow user to create account on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the create account

**Expected Result:** create_account_opened

---

## SC-004: User Registration

**Business Objective:** Allow user to user registration on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the event reinvent 2026 build whats next join us nov 30 to dec 4 in las vegas save 1200 with early bird pricing ends august 25 register today

**Expected Result:** event_reinvent_2026_build_whats_next_join_us_nov_30_to_dec_4_in_las_vegas_save_1200_with_early_bird_pricing_ends_august_25_register_today_opened

---

## SC-005: Search Products

**Business Objective:** Allow user to search products on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the industrial siemens mobility turns 175 years of data into searchable insights with aws ai view the story

**Expected Result:** industrial_siemens_mobility_turns_175_years_of_data_into_searchable_insights_with_aws_ai_view_the_story_opened

---

## SC-006: User Sign In

**Business Objective:** Allow user to user sign in on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the government solutions designed to help government agencies modernize meet mandates reduce costs and deliver mission outcomes view industry

**Expected Result:** government_solutions_designed_to_help_government_agencies_modernize_meet_mandates_reduce_costs_and_deliver_mission_outcomes_view_industry_opened

---

## SC-007: Add Item

**Business Objective:** Allow user to add item on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the telecommunications accelerate innovation scale with confidence and add agility with cloudbased telecom solutions view industry

**Expected Result:** telecommunications_accelerate_innovation_scale_with_confidence_and_add_agility_with_cloudbased_telecom_solutions_view_industry_opened

---

## SC-008: Create Account

**Business Objective:** Allow user to create account on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the create an aws account

**Expected Result:** create_an_aws_account_opened

---

## SC-009: Browse AWS_Test

**Business Objective:** Allow user to navigate the AWS_Test interface
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the filter all
2. Click the back to top
3. Click the contact us
4. Click the agentic ai data leaders use agentic ai to lead industries see how pga tour autodesk and bmw are building data foundations for agentic ai with an open architecture on aws explore how they innovate
5. Click the view more stories
6. Click the advertising  marketing pinterest drives visual discovery for 600 million monthly users building on amazon ec2 and s3 view the story
7. Click the automotive toyota reduces call handling times by 20 with amazon connect customer view the story
8. Click the financial services intuit unifies support for 100m customers with amazon connect customer view the story
9. Click the retail adidas drives enterprisewide transformation adidas accelerates application deployment 40x using aws for sap streamlining business operations and resource planning view the story
10. Click the retail tapestry amplifies store associate voices worldwide tapestry implements aws aipowered feedback analysis enabling datadriven decisions through enhanced associate insights view the story
11. Click the financial services develop innovative and secure solutions across banking capital markets insurance and payments view industry
12. Click the healthcare and life sciences accelerate innovation and improve patient care with healthcare data management and security view industry
13. Click the advertising and marketing turn data into customerwinning campaigns view industry
14. Click the manufacturing optimize production and speed timetomarket view industry
15. Click the media and entertainment transform media  entertainment with the most purposebuilt capabilities and partner solutions of any cloud view industry
16. Click the games enable game development for every genre and platform from aaa titles to indie studios view industry
17. Click the aws support overview

**Expected Result:** User reaches the intended section

---

## SC-010: Interact with AWS_Test

**Business Objective:** Allow user to interact with elements on AWS_Test
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the accept
2. Click the decline
3. Click the customize
4. Click the cancel
5. Click the element
6. Click the english
7. Click the support
8. Click the my account
9. Click the discover aws
10. Click the products
11. Click the solutions
12. Click the pricing
13. Click the resources
14. Click the show 8 more
15. Click the north america
16. Click the south america
17. Click the europe
18. Click the middle east
19. Click the africa
20. Click the asia pacific
21. Click the australia and new zealand
22. Click the geographic regions 9
23. Click the aws govcloud useast
24. Click the aws govcloud uswest
25. Click the canada central
26. Click the canada west calgary
27. Click the mexico central
28. Click the us west northern california
29. Click the us east northern virginia
30. Click the us east ohio
31. Click the us west oregon
32. Click the edge locations 31
33. Click the yes
34. Click the no
35. Click the hi i can connect you with an aws representative or answer questions you have on aws
36. Click the 1
37. Click the aws cookie notice
38. Click the cookie notice
39. Click the here
40. Click the aws privacy notice
41. Click the skip to main content
42. Click the aws marketplace
43. Click the reinvent
44. Click the start free with aws
45. Click the artificial intelligence ai find your ai path with aws startups from the first idea to scaled product discover ai tools credits and expert guidance matched to your startup stage explore ai for startups
46. Click the explore aws for your industry
47. Click the what is aws
48. Click the what is cloud computing
49. Click the what is agentic ai
50. Click the cloud computing concepts hub
51. Click the aws cloud security
52. Click the whats new
53. Click the blogs
54. Click the press releases
55. Click the getting started
56. Click the training
57. Click the aws trust center
58. Click the aws solutions library
59. Click the architecture center
60. Click the product and technical faqs
61. Click the analyst reports
62. Click the aws partners
63. Click the builder center
64. Click the sdks  tools
65. Click the net on aws
66. Click the python on aws
67. Click the java on aws
68. Click the php on aws
69. Click the javascript on aws
70. Click the file a support ticket
71. Click the aws repost
72. Click the knowledge center
73. Click the aws accessibility
74. Click the legal
75. Click the event code of conduct
76. Click the event terms  conditions
77. Click the privacy
78. Click the site terms
79. Click the cookie preferences
80. Click the retail

**Expected Result:** Interaction completes as expected

---
