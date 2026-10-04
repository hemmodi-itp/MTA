# Feature: Contrast Security - Home Page

**Feature ID:** CS-HOME-001

**Module:** Homepage

**Application:** Contrast Security

**URL:** https://www.contrastsecurity.com/

**Actor:** Guest User

---

## Background

Given the user opens the Contrast Security homepage
And the homepage is fully loaded

---

## TC-001 - Verify Homepage Loads Successfully

Scenario: Load the homepage
    Then the Contrast Security logo should be visible
    And the top navigation bar should be displayed
    And the hero banner should be displayed
    And the "Try Contrast" button should be visible

---

## TC-002 - Verify Products Menu

Scenario: Open Products menu
    When the user clicks the "Products" menu
    Then the Products dropdown should be displayed

---

## TC-003 - Verify Solutions Menu

Scenario: Open Solutions menu
    When the user clicks the "Solutions" menu
    Then the Solutions dropdown should be displayed

---

## TC-004 - Verify Partner Menu

Scenario: Open Partner menu
    When the user clicks the "Partner" menu
    Then the Partner dropdown should be displayed

---

## TC-005 - Verify Customers Navigation

Scenario: Navigate to Customers page
    When the user clicks "Customers"
    Then the Customers page should open

---

## TC-006 - Verify Company Menu

Scenario: Open Company menu
    When the user clicks the "Company" menu
    Then the Company dropdown should be displayed

---

## TC-007 - Verify Resources Menu

Scenario: Open Resources menu
    When the user clicks the "Resources" menu
    Then the Resources dropdown should be displayed

---

## TC-008 - Verify Login Navigation

Scenario: Open Login page
    When the user clicks the "Login" link
    Then the Login page should open

---

## TC-009 - Verify Contact Us Navigation

Scenario: Open Contact Us page
    When the user clicks the "Contact us" link
    Then the Contact Us page should open

---

## TC-010 - Verify Search Icon

Scenario: Open search
    When the user clicks the Search icon
    Then the search interface should be displayed

---

## TC-011 - Verify Hero CTA

Scenario: Click Try Contrast button
    When the user clicks the "Try Contrast" button
    Then the Try Contrast page should open

---

## TC-012 - Verify News Banner CTA

Scenario: Open latest news
    When the user clicks the "Read more" button
    Then the related news article should open

---

## TC-013 - Verify Hero Content

Scenario: Validate hero section
    Then the hero heading should be displayed
    And the hero description should be visible
    And the primary CTA should be enabled

---

## TC-014 - Verify Chat Widget Opens

Scenario: Interact with chatbot
    When the user clicks inside the Claire chat widget
    Then the chat input should receive focus

---

## TC-015 - Verify Book a Meeting Button

Scenario: Open meeting booking
    When the user clicks "Book a meeting"
    Then the meeting scheduling page or dialog should open

---

## TC-016 - Verify Chat Text Input

Scenario: Enter a chatbot question
    When the user enters "What products do you offer?"
    Then the entered text should appear in the chatbot input field

---

## TC-017 - Verify Chat Send Button

Scenario: Submit chatbot question
    Given the chatbot input contains a valid question
    When the user clicks the Send button
    Then the question should be submitted
    And a chatbot response should begin generating

---

## TC-018 - Verify Voice Input

Scenario: Activate voice input
    When the user clicks the Microphone button
    Then the browser microphone permission should be requested

---

## TC-019 - Verify Keyboard Navigation

Scenario: Navigate using keyboard
    When the user presses the Tab key repeatedly
    Then focus should move sequentially through all interactive controls
    And each focused element should display a visible focus indicator

---

## TC-020 - Verify Logo Navigation

Scenario: Return to homepage
    When the user clicks the Contrast Security logo
    Then the homepage should be displayed