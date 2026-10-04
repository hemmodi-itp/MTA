# Business Requirements Document — Module 0: Login

## 1. Purpose

This module validates the login flow for the AppEvolve application. Users must authenticate via Keycloak SSO before accessing any protected pages. This module covers the full sign-in journey from the landing page to the authenticated dashboard.

---

## 2. Login Flow Overview

| Step | Description |
|------|-------------|
| Landing page | `https://pt-dev.appevolve.intuitive.ai/` — presents a Sign In button |
| Keycloak form | Clicking Sign In redirects to the Keycloak login form with username/password fields |
| Submission | User fills credentials and clicks the login button |
| Post-login | Successful login redirects to `https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard` |

---

## 3. Actors

| Actor | Description |
|-------|-------------|
| Registered user | Has a valid username and password in Keycloak |
| Unregistered user | No account — login should fail gracefully |
| Automated test agent | The test runner executing this suite |

---

## 4. Business Scenarios

### BS-L01: Successful Login with Valid Credentials
- **Actor**: Registered user
- **Precondition**: User is on the landing page, not logged in
- **Steps**:
  1. Click the Sign In button on the landing page
  2. Enter valid username
  3. Enter valid password
  4. Click the login/submit button
- **Expected result**: User is redirected to the AppEvolve dashboard
- **Business rules**: Credentials must match an active Keycloak account

### BS-L02: Login Attempt with Invalid Password
- **Actor**: Registered user
- **Precondition**: User is on the Keycloak login form
- **Steps**:
  1. Enter valid username
  2. Enter incorrect password
  3. Click the login/submit button
- **Expected result**: Error message displayed, user remains on login form
- **Business rules**: No redirect on failure; error must be visible

### BS-L03: Login Attempt with Empty Credentials
- **Actor**: Any user
- **Precondition**: User is on the Keycloak login form
- **Steps**:
  1. Leave username empty
  2. Leave password empty
  3. Click the login/submit button
- **Expected result**: Form validation error displayed
- **Business rules**: Both fields are required

### BS-L04: Login Attempt with Empty Password Only
- **Actor**: Any user
- **Precondition**: User is on the Keycloak login form
- **Steps**:
  1. Enter valid username
  2. Leave password empty
  3. Click the login/submit button
- **Expected result**: Validation error on password field
- **Business rules**: Password field is required

### BS-L05: Login Page Loads Correctly
- **Actor**: Any user
- **Precondition**: User navigates to the landing page URL directly
- **Steps**:
  1. Open `https://pt-dev.appevolve.intuitive.ai/`
- **Expected result**: Sign In button is visible and clickable
- **Business rules**: Landing page must be accessible without authentication

---

## 5. Field Constraints

| Field | Constraint |
|-------|-----------|
| Username | Required; text input; max 255 characters |
| Password | Required; password input (masked); max 255 characters |

---

## 6. Out of Scope

- Password reset / forgot password flow
- Account registration
- SSO via third-party providers
- Session expiry and re-login
