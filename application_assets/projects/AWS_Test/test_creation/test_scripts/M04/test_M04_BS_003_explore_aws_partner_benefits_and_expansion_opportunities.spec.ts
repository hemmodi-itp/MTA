// Base URL (from project.yaml, resolved via playwright.config.ts): https://aws.amazon.com/partners/
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe("Explore AWS Partner benefits and expansion opportunities (M04_BS_003)", () => {

  test("positive — explore AWS Partner benefits and expansion opportunities @smoke", async ({ action }) => {
    await action.navigate();
    await action.scrollIntoView("become_an_aws_partner");
    await action.verifyVisible("become_an_aws_partner", "Why become AWS Partner section should be visible");
    await action.verifyContainsText("become_an_aws_partner", "Partner Benefits", "Partner benefits section should contain benefits heading");
    await action.verifyContainsText("become_an_aws_partner", "expansion opportunities", "Section should display expansion opportunities information");
    await action.verifyContainsText("become_an_aws_partner", "value proposition", "Section should present clear value proposition");
    await action.verifyVisible("co_sell_with_aws", "Co-sell with AWS opportunity should be visible");
    await action.verifyVisible("sell_in_aws_marketplace_2", "AWS Marketplace selling option should be visible");
  });

});
