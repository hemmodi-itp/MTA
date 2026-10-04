"""
live_login.py — performs a live browser login on every pipeline execution.

Used by PlaywrightScanner (discovery phase) and UIExecutionAgent (test execution)
when auth.strategy == "live_login" in project.yaml.

Unlike storageState / credentials strategies, this does NOT save a reusable
auth.json file. Login runs fresh on each call — the browser session stays open
so the session is immediately active for the next navigation.
"""

import os

from playwright.sync_api import Page


def perform_login(page: Page, auth_config: dict) -> None:
    """
    Execute a username/password login on an already-open Playwright page.

    Navigates to login_url, fills credentials from env vars, clicks submit,
    then waits for success_url to confirm the login completed.

    Args:
        page: An open Playwright Page object (browser session must stay open after return).
        auth_config: The auth: block from project.yaml.

    Raises:
        ValueError:   Required config fields are missing.
        RuntimeError: Env var not set, or login did not reach success_url in time.
    """
    login_url = auth_config.get("login_url") or auth_config.get("setup_url", "")
    success_url = auth_config.get("success_url") or auth_config.get("wait_for_url", "")
    username_env = auth_config.get("username_env", "")
    password_env = auth_config.get("password_env", "")
    username_selector = auth_config.get("username_selector", "")
    password_selector = auth_config.get("password_selector", "")
    submit_selector = auth_config.get("submit_selector", "")

    if not login_url:
        raise ValueError(
            "auth.login_url is required for strategy: live_login. "
            "Add it to the auth: block in project.yaml."
        )

    for env_key in filter(None, [username_env, password_env]):
        if env_key not in os.environ:
            raise RuntimeError(
                f"Environment variable '{env_key}' is not set. "
                f"Set it before running: set {env_key}=<value>  (Windows) "
                f"or export {env_key}=<value>  (Unix/Mac)"
            )

    print(f"\n[live_login] Navigating to: {login_url}")
    page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)

    signin_selector = auth_config.get("signin_selector", "") or auth_config.get("login_selector", "")
    if signin_selector:
        print(f"[live_login] Clicking sign-in button ({signin_selector})")
        page.click(signin_selector)
        print("[live_login] Waiting 3s for login form to load...")
        page.wait_for_timeout(3_000)

    if username_selector and username_env:
        print(f"[live_login] Filling username ({username_selector})")
        page.fill(username_selector, os.environ[username_env])

    if password_selector and password_env:
        print(f"[live_login] Filling password ({password_selector})")
        page.fill(password_selector, os.environ[password_env])

    if submit_selector:
        print(f"[live_login] Clicking submit ({submit_selector})")
        page.click(submit_selector)

    if success_url:
        print(f"[live_login] Waiting for post-login URL: {success_url}")
        try:
            page.wait_for_url(success_url, timeout=60_000)
            print(f"[live_login] Login confirmed — at {page.url}")
        except Exception as exc:
            raise RuntimeError(
                f"[live_login] Login did not complete — timed out waiting for '{success_url}'. "
                f"Current URL: {page.url}. Error: {exc}"
            ) from exc
    else:
        page.wait_for_timeout(2_000)
        print(f"[live_login] Login submitted — current URL: {page.url}")
