# Feature: Gemini Home Page - User Interaction

**Feature ID:** GEM-HOME-001

**Module:** Gemini Home Page

**Application:** Google Gemini

**Background**

Given the user is logged into Gemini
And the Gemini Home page is displayed

---

## TC-001 - Verify Home Page Loads Successfully

Scenario: Load Gemini Home Page
    When the user opens the Gemini Home page
    Then the prompt textbox should be visible
    And the Model selector should be visible
    And the Microphone button should be visible
    And the Sidebar should be visible

---

## TC-002 - Enter Text into Prompt

Scenario: Enter text into the prompt textbox
    When the user enters "Hello Gemini"
    Then the entered text should be displayed in the prompt textbox

---

## TC-003 - Submit Prompt using Submit Button

Scenario: Submit a valid prompt using the Submit button
    Given the user enters "Explain Artificial Intelligence"
    When the user clicks the Submit button
    Then the prompt should appear in the conversation
    And the AI response should begin generating

---

## TC-004 - Submit Prompt using Enter Key

Scenario: Submit prompt using Enter
    Given the user enters "Hello World"
    When the user presses Enter
    Then the prompt should be submitted
    And the AI response should begin generating

---

## TC-005 - Verify Shift + Enter Inserts New Line

Scenario: Create a multiline prompt
    Given the prompt textbox is focused
    When the user enters "Hello"
    And presses Shift + Enter
    And enters "Gemini"
    Then the prompt textbox should contain two lines
    And the prompt should not be submitted

---

## TC-006 - Verify Submit Button Disabled for Empty Prompt

Scenario: Empty prompt validation
    Given the prompt textbox is empty
    Then the Submit button should remain disabled

---

## TC-007 - Verify Submit Button Disabled for Whitespaces

Scenario: Whitespace validation
    When the user enters only blank spaces
    Then the Submit button should remain disabled

---

## TC-008 - Verify Model Dropdown Opens

Scenario: Open model selector
    When the user clicks the Model dropdown
    Then the list of available models should be displayed

---

## TC-009 - Select Different AI Model

Scenario: Change AI model
    Given the Model dropdown is open
    When the user selects another available model
    Then the selected model should become active

---

## TC-010 - Verify Upgrade Button Navigation

Scenario: Open Upgrade page
    When the user clicks the Upgrade button
    Then the Upgrade dialog or subscription page should be displayed

---

## TC-011 - Verify Sidebar Collapse

Scenario: Collapse sidebar
    When the user clicks the Sidebar toggle
    Then the Sidebar should collapse

---

## TC-012 - Verify Sidebar Expansion

Scenario: Expand sidebar
    Given the Sidebar is collapsed
    When the user clicks the Sidebar toggle
    Then the Sidebar should expand

---

## TC-013 - Verify New Chat

Scenario: Start a new conversation
    When the user clicks the New Chat button
    Then a new conversation should be created
    And the prompt textbox should be empty

---

## TC-014 - Open Previous Conversation

Scenario: Open conversation from history
    Given previous conversations are available
    When the user clicks a conversation in the Sidebar
    Then the selected conversation should open

---

## TC-015 - Verify Settings Opens

Scenario: Open Settings
    When the user clicks the Settings icon
    Then the Settings panel should be displayed

---

## TC-016 - Verify Search Opens

Scenario: Open Search
    When the user clicks the Search icon
    Then the Search interface should be displayed

---

## TC-017 - Verify Keyboard Tab Navigation

Scenario: Navigate using keyboard
    When the user repeatedly presses the Tab key
    Then the focus should move sequentially through all interactive controls

---

## TC-018 - Verify Microphone Button Click

Scenario: Open voice input
    When the user clicks the Microphone button
    Then the microphone interface or permission dialog should be displayed

---

## TC-019 - Verify Response Generation

Scenario: Generate AI response
    Given the user submits a valid prompt
    Then a loading indicator should be displayed
    And the AI response should be generated
    And the response should be displayed

---

## TC-020 - Verify Refresh Retains Conversation

Scenario: Refresh browser
    Given a conversation has already been created
    When the user refreshes the page
    Then the conversation should remain available
    And the chat history should be preserved