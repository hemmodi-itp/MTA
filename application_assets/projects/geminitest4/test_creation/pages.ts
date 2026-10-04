// AUTO-GENERATED from locator_map.json — do not hand-edit.
// To fix a locator: edit locator_map.json (or rerun discovery), then regenerate this file.
import { Page, Locator } from '@playwright/test';
import { LocatorManager } from '../../../_shared/runtime/LocatorManager';

export class HomepagePage {
  constructor(private readonly page: Page) {}

  get a_loc_0017(): Locator { return LocatorManager.resolve(this.page, "a_loc_0017"); }
  get about_gemini_opens_in_a_new_window(): Locator { return LocatorManager.resolve(this.page, "about_gemini_opens_in_a_new_window"); }
  get flash(): Locator { return LocatorManager.resolve(this.page, "flash"); }
  get for_business_opens_in_a_new_window(): Locator { return LocatorManager.resolve(this.page, "for_business_opens_in_a_new_window"); }
  get gemini(): Locator { return LocatorManager.resolve(this.page, "gemini"); }
  get get_gemini_app_opens_in_a_new_window(): Locator { return LocatorManager.resolve(this.page, "get_gemini_app_opens_in_a_new_window"); }
  get google_apps(): Locator { return LocatorManager.resolve(this.page, "google_apps"); }
  get google_privacy_policy_opens_in_a_new_window(): Locator { return LocatorManager.resolve(this.page, "google_privacy_policy_opens_in_a_new_window"); }
  get google_terms_opens_in_a_new_window(): Locator { return LocatorManager.resolve(this.page, "google_terms_opens_in_a_new_window"); }
  get listen(): Locator { return LocatorManager.resolve(this.page, "listen"); }
  get microphone(): Locator { return LocatorManager.resolve(this.page, "microphone"); }
  get new_chat(): Locator { return LocatorManager.resolve(this.page, "new_chat"); }
  get open_sidebar(): Locator { return LocatorManager.resolve(this.page, "open_sidebar"); }
  get settings(): Locator { return LocatorManager.resolve(this.page, "settings"); }
  get sign_in(): Locator { return LocatorManager.resolve(this.page, "sign_in"); }
  get sign_in_2(): Locator { return LocatorManager.resolve(this.page, "sign_in_2"); }
  get sign_in_3(): Locator { return LocatorManager.resolve(this.page, "sign_in_3"); }
  get subscriptions_opens_in_a_new_window(): Locator { return LocatorManager.resolve(this.page, "subscriptions_opens_in_a_new_window"); }
  get upload_tools(): Locator { return LocatorManager.resolve(this.page, "upload_tools"); }
}

export const PAGE_REGISTRY: Record<string, new (page: Page) => Record<string, unknown>> = {
  "M01": HomepagePage,
};
