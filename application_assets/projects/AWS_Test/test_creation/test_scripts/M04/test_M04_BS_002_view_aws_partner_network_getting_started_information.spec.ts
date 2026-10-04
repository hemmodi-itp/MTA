// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/partners/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("View AWS Partner Network getting started information (M04_BS_002)", () => {

  test("positive — view AWS Partner Network getting started information @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("aws_partner_central");
    await action.click("aws_partner_central");
    await action.verifyUrl("/partners/partner-network", "User should navigate to the AWS Partner Network section");
    await action.verifyContainsText("aws_partner_central", "Getting Started with AWS Partner Network", "Getting started heading should be visible");
    await action.verifyContainsText("explore_partner_programs", "Join the AWS Partner Network to grow your business", "Partner network guidance content should be displayed");
    await action.verifyContainsText("partner_paths", "Apply now to become an AWS Partner", "Clear next steps should be provided to users");
  });

  test("negative — key partner network content missing or incorrect @regression", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("aws_partner_central");
    await action.click("aws_partner_central");
    await action.verifyUrl("/partners/partner-network", "User should navigate to the AWS Partner Network section");
    await action.verifyContainsText("aws_partner_central", "", "Partner Network getting started section heading should not be empty");
  });

});
