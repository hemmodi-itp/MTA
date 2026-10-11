import { describe, expect, it } from "vitest";
import type { Transition, Variants } from "framer-motion";
import {
  animatesAt, duration, ease, fadeIn, fadeUp, flipDelta, listItem, page, scaleIn, slideInRight, STAGGER_CAP, transition, tweenValue,
} from "./motion";

const variants: Record<string, Variants> = { fadeIn, fadeUp, scaleIn, slideInRight, page, listItem };
const timing = (v: Variants, state: string) => (v[state] as { transition?: Transition } | undefined)?.transition as
  | { duration?: number; ease?: readonly number[] }
  | undefined;

describe("motion tokens follow the brief", () => {
  it("micro-interactions take 120–200 ms", () => {
    for (const d of [duration.fast, duration.micro, duration.exit]) {
      expect(d).toBeGreaterThanOrEqual(0.12);
      expect(d).toBeLessThanOrEqual(0.2);
    }
  });

  it("panels and pages take 200–350 ms", () => {
    for (const d of [duration.panel, duration.page]) {
      expect(d).toBeGreaterThanOrEqual(0.2);
      expect(d).toBeLessThanOrEqual(0.35);
    }
  });

  it("every preset enters with ease-out within 350 ms", () => {
    for (const [name, v] of Object.entries(variants)) {
      const show = timing(v, "show");
      expect(show?.duration, name).toBeLessThanOrEqual(0.35);
      expect(show?.ease, name).toEqual(ease.enter);
    }
  });

  it("exits are ease-in and faster than entrances", () => {
    for (const [name, v] of Object.entries(variants)) {
      const exit = timing(v, "exit");
      if (!exit) continue;
      expect(exit.ease, name).toEqual(ease.exit);
      expect(exit.duration!, name).toBeLessThan(timing(v, "show")!.duration!);
    }
    expect(transition.exit.duration).toBeLessThan(transition.enter.duration);
  });

  it("enter presets only move and fade (transform + opacity)", () => {
    const allowed = new Set(["opacity", "x", "y", "scale", "transition"]);
    for (const [name, v] of Object.entries(variants)) {
      for (const state of ["hidden", "show", "exit"]) {
        for (const key of Object.keys((v[state] as object | undefined) ?? {})) expect(allowed.has(key), `${name}.${state}.${key}`).toBe(true);
      }
    }
  });
});

describe("list stagger cap", () => {
  it("animates only the first 20 items of a list", () => {
    expect(STAGGER_CAP).toBe(20);
    expect(animatesAt(0)).toBe(true);
    expect(animatesAt(19)).toBe(true);
    expect(animatesAt(20)).toBe(false);
    expect(animatesAt(500)).toBe(false);
  });
});

describe("flipDelta (sliding indicator)", () => {
  it("maps the new box back onto the old one", () => {
    expect(flipDelta({ left: 0, top: 0, width: 100, height: 40 }, { left: 50, top: 10, width: 200, height: 40 })).toEqual({
      x: -50, y: -10, scaleX: 0.5, scaleY: 1,
    });
  });

  it("is the identity when nothing moved", () => {
    const box = { left: 12, top: 30, width: 80, height: 32 };
    expect(flipDelta(box, box)).toEqual({ x: 0, y: 0, scaleX: 1, scaleY: 1 });
  });

  it("never divides by zero for a box that has no size yet", () => {
    expect(flipDelta({ left: 0, top: 0, width: 10, height: 10 }, { left: 0, top: 0, width: 0, height: 0 })).toEqual({
      x: 0, y: 0, scaleX: 1, scaleY: 1,
    });
  });
});

describe("tweenValue (count-up)", () => {
  it("starts at `from` and lands exactly on `to`", () => {
    expect(tweenValue(0, 74, 0)).toBe(0);
    expect(tweenValue(0, 74, 1)).toBe(74);
    expect(tweenValue(10, 3, 1)).toBe(3);
  });

  it("clamps progress outside 0–1", () => {
    expect(tweenValue(0, 50, -1)).toBe(0);
    expect(tweenValue(0, 50, 7)).toBe(50);
  });

  it("only ever moves towards the target (ease-out, no overshoot)", () => {
    let prev = -Infinity;
    for (let p = 0; p <= 1; p += 0.05) {
      const v = tweenValue(0, 100, p);
      expect(v).toBeGreaterThanOrEqual(prev);
      expect(v).toBeLessThanOrEqual(100);
      prev = v;
    }
  });
});
