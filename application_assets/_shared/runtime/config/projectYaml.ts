// projectYaml.ts — read application_assets/projects/<PW_PROJECT>/project.yaml (Phase 4).
//
// Used by the config builder (matrix, test-id attribute, locale, reporters) and by the `role` fixture
// (auth.roles). Parsed with the `yaml` package; a missing or unparsable file is `null`, never an error:
// a hand run without PW_PROJECT keeps Playwright's defaults. Base-URL resolution keeps its own line
// scanner (baseUrl.ts, Phase 0.6) unchanged.

import fs from 'fs';
import path from 'path';
import { parse } from 'yaml';

export function projectYamlPath(project: string, cwd: string = process.cwd()): string {
  return path.join(cwd, 'application_assets', 'projects', project, 'project.yaml');
}

export function parseProjectYaml(text: string | null): Record<string, any> | null {
  if (text === null) return null;
  try {
    const doc = parse(text);
    return doc && typeof doc === 'object' && !Array.isArray(doc) ? doc : null;
  } catch {
    return null;
  }
}

const cache = new Map<string, Record<string, any> | null>();

export function loadProjectYaml(project: string | undefined, cwd: string = process.cwd()): Record<string, any> | null {
  if (!project) return null;
  const file = projectYamlPath(project, cwd);
  if (!cache.has(file)) {
    cache.set(file, parseProjectYaml(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null));
  }
  return cache.get(file) ?? null;
}
