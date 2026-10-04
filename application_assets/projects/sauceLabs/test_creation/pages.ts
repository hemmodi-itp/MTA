// AUTO-GENERATED from locator_map.json — do not hand-edit.
// To fix a locator: edit locator_map.json (or rerun discovery), then regenerate this file.
import { Page, Locator } from '@playwright/test';
import { LocatorManager } from '../../../_shared/runtime/LocatorManager';

export class DefaultPage {
  constructor(private readonly page: Page) {}

  get input_loc_0003(): Locator { return LocatorManager.resolve(this.page, "input_loc_0003"); }
  get password(): Locator { return LocatorManager.resolve(this.page, "password"); }
  get username(): Locator { return LocatorManager.resolve(this.page, "username"); }
}

export const PAGE_REGISTRY: Record<string, new (page: Page) => Record<string, unknown>> = {
  "_default": DefaultPage,
};
