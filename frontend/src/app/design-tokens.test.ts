import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/*
 * WCAG AA guard for the colour tokens in globals.css, in light and dark. Text needs 4.5:1 against everything it sits
 * on: the card, the page, muted panels and — for status text — its own tinted pill background.
 */

const css = readFileSync(fileURLToPath(new URL("./globals.css", import.meta.url)), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.search(new RegExp(`^${selector.replace(/[.[\]]/g, "\\$&")}\\s*\\{`, "m"));
  if (start < 0) throw new Error(`no ${selector} block in globals.css`);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("\n}", start));
  return Object.fromEntries([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map(([, k, v]) => [k, v.trim()]));
}

type RGB = [number, number, number];
const hex = (value: string | undefined, name: string): RGB => {
  const m = value?.match(/^#([0-9a-f]{6})$/i);
  if (!m) throw new Error(`--${name} is not a #rrggbb colour: ${value}`);
  return [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) as RGB;
};
const mix = (fg: RGB, bg: RGB, amount: number): RGB => fg.map((v, i) => v * amount + bg[i] * (1 - amount)) as RGB;
const luminance = (rgb: RGB) => {
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a: RGB, b: RGB) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const WHITE: RGB = [255, 255, 255];
const TONES = ["success", "warning", "critical", "info", "neutral", "violet", "orange"];

for (const theme of [":root", ".dark"] as const) {
  const t = block(theme);
  const c = (name: string) => hex(t[name], name);
  const background = c("background");
  // cards are 86 % opaque over the page (.surface-card)
  const card = mix(c("card"), background, 0.86);
  const tintPct = parseFloat(t["tint-pct"]) / 100;

  describe(`${theme === ":root" ? "light" : "dark"} theme contrast`, () => {
    it("body and secondary text read on every surface", () => {
      for (const [name, surface] of [["background", background], ["card", card], ["muted", c("muted")]] as const) {
        expect(contrast(c("foreground"), surface), `foreground on ${name}`).toBeGreaterThanOrEqual(4.5);
        expect(contrast(c("muted-foreground"), surface), `muted-foreground on ${name}`).toBeGreaterThanOrEqual(4.5);
      }
    });

    it.each(TONES)("%s text reads on the card and on its own tint", (tone) => {
      const base = c(tone);
      const fg = c(`${tone}-fg`);
      expect(tintPct).toBeGreaterThan(0);
      expect(contrast(fg, card), `${tone}-fg on card`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(fg, background), `${tone}-fg on page`).toBeGreaterThanOrEqual(4.5);
      expect(contrast(fg, mix(base, card, tintPct)), `${tone}-fg on ${tone} tint`).toBeGreaterThanOrEqual(4.5);
    });

    it("white text reads on solid fills (buttons, badges)", () => {
      expect(contrast(WHITE, c("primary-solid")), "white on primary-solid").toBeGreaterThanOrEqual(4.5);
      expect(contrast(WHITE, c("primary-solid-hover")), "white on primary-solid-hover").toBeGreaterThanOrEqual(4.5);
      expect(contrast(WHITE, c("critical-solid")), "white on critical-solid").toBeGreaterThanOrEqual(4.5);
    });

    it("links and destructive text read on the card", () => {
      expect(contrast(c("primary"), card), "primary text on card").toBeGreaterThanOrEqual(4.5);
      expect(contrast(c("destructive"), card), "destructive text on card").toBeGreaterThanOrEqual(4.5);
    });

    it("focus rings and status fills stand out from the card (3:1 for UI)", () => {
      expect(contrast(c("ring"), card), "ring").toBeGreaterThanOrEqual(3);
      for (const tone of TONES) {
        expect(contrast(c(tone), card), `${tone} fill`).toBeGreaterThanOrEqual(3);
      }
    });
  });
}
