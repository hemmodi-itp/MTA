// AUTO-GENERATED from locator_map.json — do not hand-edit.
// To fix a locator: edit locator_map.json (or rerun discovery), then regenerate this file.
import { Page, Locator } from '@playwright/test';
import { LocatorManager } from '../../../_shared/runtime/LocatorManager';

export class DefaultPage {
  constructor(private readonly page: Page) {}

  get brd_compliance_criterion_level(): Locator { return LocatorManager.resolve(this.page, "brd_compliance_criterion_level"); }
  get delete(): Locator { return LocatorManager.resolve(this.page, "delete"); }
  get new_project(): Locator { return LocatorManager.resolve(this.page, "new_project"); }
  get new_project_2(): Locator { return LocatorManager.resolve(this.page, "new_project_2"); }
  get open(): Locator { return LocatorManager.resolve(this.page, "open"); }
  get open_the_demo_project(): Locator { return LocatorManager.resolve(this.page, "open_the_demo_project"); }
  get shopflow_demo(): Locator { return LocatorManager.resolve(this.page, "shopflow_demo"); }
  get switch_to_dark_mode(): Locator { return LocatorManager.resolve(this.page, "switch_to_dark_mode"); }
}

export const PAGE_REGISTRY: Record<string, new (page: Page) => Record<string, unknown>> = {
  "_default": DefaultPage,
};
