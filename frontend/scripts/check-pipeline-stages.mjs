#!/usr/bin/env node
/**
 * Fails (exit 1) when the pipeline stage lists drift apart:
 *   - enum PipelineStage in prisma/schema.prisma (the DB enum),
 *   - the PipelineStage union in src/lib/types.ts (the UI),
 *   - the stage values in api/pipeline.py STEP_META (what the Python service writes; read-only here, parsed as text).
 * The Prisma enum and the TS union must match exactly; every STEP_META stage must exist in both
 * (the enum also keeps legacy stages STEP_META no longer emits).
 * Run: npm run lint:schema
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(resolve(root, p), "utf8");
const stripComments = (s) => s.replace(/\/\/.*$/gm, "");

function prismaStages() {
  const m = read("prisma/schema.prisma").match(/enum\s+PipelineStage\s*\{([\s\S]*?)\}/);
  if (!m) throw new Error("enum PipelineStage not found in prisma/schema.prisma");
  return stripComments(m[1]).split(/\s+/).filter(Boolean);
}

function tsStages() {
  const m = read("src/lib/types.ts").match(/export\s+type\s+PipelineStage\s*=([\s\S]*?);/);
  if (!m) throw new Error("type PipelineStage not found in src/lib/types.ts");
  return [...stripComments(m[1]).matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
}

function pythonStages() {
  const src = read("../api/pipeline.py");
  const m = src.match(/STEP_META[^=]*=\s*\{([\s\S]*?)\n\}/);
  if (!m) throw new Error("STEP_META not found in api/pipeline.py");
  // "agent_key": ("stage", "Label"),
  return [...new Set([...m[1].matchAll(/^\s*["'][\w-]+["']\s*:\s*\(\s*["']([a-z_]+)["']/gm)].map((x) => x[1]))];
}

const diff = (a, b) => a.filter((x) => !b.includes(x));
const prisma = prismaStages();
const ts = tsStages();
const py = pythonStages();
const problems = [];

if (!py.length) problems.push("No stages parsed from api/pipeline.py STEP_META (format changed?)");
for (const s of diff(prisma, ts)) problems.push(`"${s}" is in prisma enum PipelineStage but not in the TS PipelineStage union`);
for (const s of diff(ts, prisma)) problems.push(`"${s}" is in the TS PipelineStage union but not in prisma enum PipelineStage`);
for (const s of diff(py, prisma)) problems.push(`"${s}" is written by api/pipeline.py STEP_META but missing from prisma enum PipelineStage (needs a migration)`);
for (const s of diff(py, ts)) problems.push(`"${s}" is written by api/pipeline.py STEP_META but missing from the TS PipelineStage union`);
for (const [name, list] of [["prisma", prisma], ["types.ts", ts]]) {
  const dupes = list.filter((s, i) => list.indexOf(s) !== i);
  if (dupes.length) problems.push(`duplicate stages in ${name}: ${dupes.join(", ")}`);
}

if (problems.length) {
  console.error(`PipelineStage check failed:\n  - ${problems.join("\n  - ")}`);
  process.exit(1);
}
console.log(`PipelineStage check passed: ${prisma.length} enum values, ${ts.length} TS values, ${py.length} STEP_META stages.`);
