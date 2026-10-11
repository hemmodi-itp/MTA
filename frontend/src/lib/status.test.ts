import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ACTIVE_RUN_STATUSES, FINISHED_RUN_STATUSES } from "./run-status";
import { BAND_TONE, SEMANTIC_STATUSES, SEMANTIC_TONE, statusMeta, TONE_CLASS, TONES } from "./status";

const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");

// Every value the API can send. The registry is typed against the same unions, so a new status fails the build too.
const RUN = [...ACTIVE_RUN_STATUSES, ...FINISHED_RUN_STATUSES];
const TEST = ["passed", "failed", "inconclusive", "not_executed", "pending", "healed", "skipped"];
const STEP = ["pending", "running", "success", "failed", "skipped"];

describe("status registry", () => {
  it("has the eight semantic statuses, each with a tone", () => {
    expect([...SEMANTIC_STATUSES].sort()).toEqual(["failed", "flaky", "healed", "inconclusive", "passed", "queued", "running", "skipped"]);
    for (const s of SEMANTIC_STATUSES) expect(TONES).toContain(SEMANTIC_TONE[s]);
  });

  it("gives every run, test and step status a label, a semantic status and a tone", () => {
    for (const key of [...RUN, ...TEST, ...STEP]) {
      const meta = statusMeta(key);
      expect(meta.label.length, key).toBeGreaterThan(0);
      expect(meta.semantic, key).not.toBeNull();
      expect(TONES, key).toContain(meta.tone);
    }
  });

  it("treats every active run phase as running except queued", () => {
    for (const s of ACTIVE_RUN_STATUSES) expect(statusMeta(s).semantic).toBe(s === "queued" ? "queued" : "running");
    expect(statusMeta("completed").semantic).toBe("passed");
    expect(statusMeta("failed").semantic).toBe("failed");
    expect(statusMeta("cancelled").semantic).toBe("skipped");
  });

  it("uses the same tone for the same outcome everywhere", () => {
    expect(statusMeta("failed").tone).toBe("critical");
    expect(statusMeta("passed").tone).toBe("success");
    expect(statusMeta("success").tone).toBe("success");
    expect(statusMeta("running").tone).toBe("info");
    expect(statusMeta("inconclusive").tone).toBe("warning");
    expect(statusMeta("healed").tone).toBe("violet");
    expect(statusMeta("flaky").tone).toBe("orange");
  });

  it("maps risk levels and score bands onto tones", () => {
    expect(statusMeta("low")).toMatchObject({ tone: "success", semantic: null });
    expect(statusMeta("medium").tone).toBe("warning");
    expect(statusMeta("high").tone).toBe("critical");
    expect(BAND_TONE).toEqual({ good: "success", warn: "warning", bad: "critical", none: "neutral" });
  });

  it("renders unknown values neutrally instead of crashing", () => {
    expect(statusMeta("something_new")).toMatchObject({ label: "something new", tone: "neutral", semantic: null });
  });

  it("has a tone utility in globals.css for every tone class", () => {
    for (const tone of TONES) {
      expect(TONE_CLASS[tone]).toBe(`tone-${tone}`);
      expect(css, tone).toMatch(new RegExp(`@utility tone-${tone}\\s*\\{`));
    }
  });
});
