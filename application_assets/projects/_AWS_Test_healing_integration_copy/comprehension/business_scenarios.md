# Business Scenarios — AWS_Test

Total: **21 scenario(s)**

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
5. Click the save preferences

**Expected Result:** save_preferences_opened

---

## SC-002: Browse AWS_Test

**Business Objective:** Allow user to navigate the AWS_Test interface
**Actor:** User
**Confidence:** 75%

**Preconditions:**
- AWS_Test page is loaded

**Steps:**
1. Click the filter all

**Expected Result:** User reaches the intended section

---

## SC-003: Interact with AWS_Test

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
14. Click the play

**Expected Result:** Interaction completes as expected

---

## SC-004: Interact with AWS_Test

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
14. Click the play
15. Click the skip forward
16. Click the mute
17. Click the seek to live currently behind livelive
18. Click the chapters
19. Click the descriptions
20. Click the captions
21. Click the audio track
22. Click the pictureinpicture
23. Click the fullscreen
24. Click the reset
25. Click the done
26. Click the close modal dialog
27. Click the modernize enterprise applications
28. Click the build saas applications
29. Click the deploy globally distributed applications
30. Click the go serverless
31. Click the need more info highlight any text to get an explanation generated with aws generative ai
32. Click the 2

**Expected Result:** Interaction completes as expected

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

**Expected Result:** Interaction completes as expected

---
