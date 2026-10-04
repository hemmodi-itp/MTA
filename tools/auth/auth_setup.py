"""
auth_setup.py — one-time Playwright auth state capture.

Supports two strategies:
  credentials   — fills login form automatically from env vars; fully unattended
  storageState  — opens headed browser, waits for user to complete SSO/OAuth login

Both produce an auth.json (cookies + localStorage) that is reused by every
subsequent Playwright context (DOM scanner and generated test specs).

Usage:
    python main.py --project <name> --auth-setup
"""

import os
import sys
from typing import Optional

import yaml
from playwright.sync_api import sync_playwright

from tools.constants import PROJECTS_BASE as _ASSETS_BASE


def run_auth_setup(project_name: str) -> str:
    """
    Execute auth setup for the given project.

    Reads auth: block from project.yaml, opens a browser, completes login,
    saves storageState to auth.storage_state_path, and returns that path.

    Raises:
        FileNotFoundError  — project.yaml not found
        ValueError         — auth block missing, disabled, or misconfigured
        RuntimeError       — login did not complete successfully
    """
    safe = _safe_name(project_name)
    yaml_path = os.path.join(_ASSETS_BASE, safe, "project.yaml")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(
            f"project.yaml not found at '{yaml_path}'. "
            "Ensure the project directory exists under application_assets/projects/."
        )

    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    auth = cfg.get("auth", {})
    if not auth:
        raise ValueError(
            f"No 'auth:' block found in '{yaml_path}'. "
            "Add an auth: section with enabled: true and the required fields."
        )
    if not auth.get("enabled", False):
        raise ValueError(
            f"auth.enabled is false in '{yaml_path}'. Set enabled: true to use auth setup."
        )

    strategy = auth.get("strategy", "storageState")
    setup_url = auth.get("setup_url", "")
    storage_state_path = auth.get("storage_state_path", "")
    wait_for_url = auth.get("wait_for_url", "") or ""

    if not setup_url:
        raise ValueError("auth.setup_url is required in project.yaml")
    if not storage_state_path:
        raise ValueError("auth.storage_state_path is required in project.yaml")

    # Ensure .auth/ directory exists
    auth_dir = os.path.dirname(storage_state_path)
    if auth_dir:
        os.makedirs(auth_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Auth Setup — {project_name}")
    print(f"  Strategy:  {strategy}")
    print(f"  URL:       {setup_url}")
    print(f"  Output:    {storage_state_path}")
    print(f"{'='*60}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            if strategy == "credentials":
                _login_with_credentials(page, auth, setup_url, wait_for_url)
            else:
                _login_manually(page, setup_url, wait_for_url)

            print("\nSaving auth state...")
            context.storage_state(path=storage_state_path)
            print(f"Auth state saved → {storage_state_path}")
            print("You can now run the pipeline normally. Re-run --auth-setup when the session expires.\n")

        finally:
            context.close()
            browser.close()

    return storage_state_path


def _login_with_credentials(page, auth: dict, setup_url: str, wait_for_url: str) -> None:
    """Automated credentials-based login — reads username/password from env vars."""
    username_env = auth.get("username_env", "")
    password_env = auth.get("password_env", "")
    username_selector = auth.get("username_selector", "")
    password_selector = auth.get("password_selector", "")
    submit_selector = auth.get("submit_selector", "")

    for env_key in (username_env, password_env):
        if not env_key:
            raise ValueError(
                "auth.username_env and auth.password_env are required for strategy: credentials"
            )
        if env_key not in os.environ:
            raise RuntimeError(
                f"Environment variable '{env_key}' is not set. "
                f"Export it before running: export {env_key}=<value>"
            )

    username = os.environ[username_env]
    password = os.environ[password_env]

    print(f"Navigating to {setup_url}")
    page.goto(setup_url, wait_until="domcontentloaded", timeout=30_000)

    signin_selector = auth.get("signin_selector", "") or auth.get("login_selector", "")
    if signin_selector:
        print(f"Clicking sign-in button ({signin_selector})")
        page.click(signin_selector)
        print("Waiting 3s for login form to load...")
        page.wait_for_timeout(3_000)

    if username_selector:
        print(f"Filling username ({username_selector})")
        page.fill(username_selector, username)

    if password_selector:
        print(f"Filling password ({password_selector})")
        page.fill(password_selector, password)

    if submit_selector:
        print(f"Clicking submit ({submit_selector})")
        page.click(submit_selector)

    if wait_for_url:
        print(f"Waiting for post-login URL: {wait_for_url}")
        try:
            page.wait_for_url(wait_for_url, timeout=60_000)
            print(f"Login confirmed — at {page.url}")
        except Exception as exc:
            raise RuntimeError(
                f"Login did not complete — timed out waiting for '{wait_for_url}'. "
                f"Current URL: {page.url}. Error: {exc}"
            ) from exc
    else:
        # No success URL specified — give the page a moment to settle
        page.wait_for_timeout(2_000)
        print(f"Login submitted — current URL: {page.url}")


def _login_manually(page, setup_url: str, wait_for_url: str) -> None:
    """Interactive login — opens browser, waits for user to complete SSO/OAuth."""
    print(f"Navigating to {setup_url}")
    page.goto(setup_url, wait_until="domcontentloaded", timeout=30_000)

    if wait_for_url:
        print(f"\nWaiting for URL pattern '{wait_for_url}' (indicates login complete)...")
        print("Complete your login in the browser window.")
        try:
            page.wait_for_url(wait_for_url, timeout=300_000)
            print(f"\nLogin detected — at {page.url}")
        except Exception as exc:
            raise RuntimeError(
                f"Timed out (5 min) waiting for '{wait_for_url}'. "
                f"Current URL: {page.url}."
            ) from exc
    else:
        print("\nComplete your login in the browser window.")
        print("When you are back on the application (not the login/SSO page), press Enter here...")
        try:
            input()
        except EOFError:
            # Non-interactive terminal fallback — wait 60s
            print("Non-interactive terminal detected — waiting 60 seconds...")
            page.wait_for_timeout(60_000)

    print(f"Proceeding with current URL: {page.url}")


def _safe_name(name: str) -> str:
    sanitised = "".join(
        c if (c.isalnum() or c in "-_") else "_" for c in name
    ).strip("_")
    return sanitised or "project"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m tools.auth.auth_setup <project_name>")
        sys.exit(1)
    run_auth_setup(sys.argv[1])
