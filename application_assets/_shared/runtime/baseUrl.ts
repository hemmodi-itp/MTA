// baseUrl.ts — base-URL resolution for playwright.config.ts (Phase 0.6).
//
// There is NO default. The old silent `http://localhost:3000` fallback sent
// tests to whatever listened there (often MTA's own web app). Resolution:
//   1. BASE_URL env var — set by UIExecutionAgent / SuiteOrchestrator.
//   2. project.yaml of PW_PROJECT: `project.url`, else the single distinct
//      `modules[].url`. Several distinct module URLs are ambiguous -> error.
//   3. Otherwise throw, naming what to set.
//
// project.yaml is scanned line by line (no YAML dependency): only the
// `project:` block's `url:` and each `modules:` item's own `url:` count —
// `setup_url:` / `wait_for_url:` / setup `goto:` never match.

export interface ProjectUrls {
  projectUrl: string | null;
  moduleUrls: string[];
}

function unquote(value: string): string {
  const v = value.replace(/\s+#.*$/, '').trim();
  return v.replace(/^['"]|['"]$/g, '');
}

export function scanProjectYaml(content: string): ProjectUrls {
  let section = '';
  let moduleItemIndent = -1;
  let projectUrl: string | null = null;
  const moduleUrls: string[] = [];
  for (const raw of content.split(/\r?\n/)) {
    if (!raw.trim() || raw.trim().startsWith('#')) continue;
    const indent = raw.length - raw.trimStart().length;
    if (indent === 0) {
      const top = raw.match(/^([A-Za-z_][\w-]*)\s*:/);
      section = top ? top[1] : '';
      moduleItemIndent = -1;
      continue;
    }
    if (section === 'project') {
      const m = raw.match(/^\s+url:\s*(.+)$/);
      if (m && projectUrl === null) projectUrl = unquote(m[1]) || null;
    } else if (section === 'modules') {
      const item = raw.match(/^(\s*)-\s+(.*)$/);
      if (item && (moduleItemIndent < 0 || item[1].length <= moduleItemIndent)) {
        moduleItemIndent = item[1].length;
        const inline = item[2].match(/^url:\s*(.+)$/);
        if (inline) moduleUrls.push(unquote(inline[1]));
        continue;
      }
      // A module's own keys sit exactly 2 columns right of its "- ".
      const key = raw.match(/^(\s*)url:\s*(.+)$/);
      if (key && moduleItemIndent >= 0 && key[1].length === moduleItemIndent + 2) {
        moduleUrls.push(unquote(key[2]));
      }
    }
  }
  return { projectUrl, moduleUrls: moduleUrls.filter(Boolean) };
}

export function resolveBaseUrl(
  env: Record<string, string | undefined>,
  readProjectYaml: (project: string) => string | null,
): string {
  if (env.BASE_URL && env.BASE_URL.trim()) return env.BASE_URL.trim();
  const project = env.PW_PROJECT || '';
  if (project) {
    const content = readProjectYaml(project);
    if (content !== null) {
      const { projectUrl, moduleUrls } = scanProjectYaml(content);
      if (projectUrl) return projectUrl;
      const distinct = [...new Set(moduleUrls)];
      if (distinct.length === 1) return distinct[0];
      if (distinct.length > 1) {
        throw new Error(
          `MTA: base URL ambiguous — project '${project}' has several module URLs ` +
            `(${distinct.join(', ')}) and no project.url. Set BASE_URL, or run through ` +
            '`python main.py --project <name>` which runs each module against its own URL.',
        );
      }
    }
  }
  throw new Error(
    'MTA: base URL unresolved — set BASE_URL, or PW_PROJECT with project.url / modules[].url ' +
      'in project.yaml. (There is no localhost:3000 fallback any more.)',
  );
}
