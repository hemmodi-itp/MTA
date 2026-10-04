// AUTO-GENERATED from locator_map.json — do not hand-edit.
// To fix a locator: edit locator_map.json (or rerun discovery), then regenerate this file.
import { Page, Locator } from '@playwright/test';
import { LocatorManager } from '../../../_shared/runtime/LocatorManager';

export class DefaultPage {
  constructor(private readonly page: Page) {}

  get a_loc_0005(): Locator { return LocatorManager.resolve(this.page, "a_loc_0005"); }
  get a_loc_0006(): Locator { return LocatorManager.resolve(this.page, "a_loc_0006"); }
  get a_loc_0007(): Locator { return LocatorManager.resolve(this.page, "a_loc_0007"); }
  get button_loc_0001(): Locator { return LocatorManager.resolve(this.page, "button_loc_0001"); }
  get deploy(): Locator { return LocatorManager.resolve(this.page, "deploy"); }
  get link_to_heading(): Locator { return LocatorManager.resolve(this.page, "link_to_heading"); }
  get main_menu(): Locator { return LocatorManager.resolve(this.page, "main_menu"); }
  get stop(): Locator { return LocatorManager.resolve(this.page, "stop"); }
}

export const PAGE_REGISTRY: Record<string, new (page: Page) => Record<string, unknown>> = {
  "_default": DefaultPage,
};
