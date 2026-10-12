// roles.ts — `test.use({ role: 'admin' })` -> the storageState that role's tests start with (Phase 4.3).
//
// Roles are project.yaml `auth.roles` (the Phase 2 block, tools/discovery/deep/config.py):
//   anonymous     -> an empty storage state (no cookies, no localStorage)
//   storageState  -> the role's own storage_state_path
//   credentials / setup -> application_assets/projects/<project>/.auth/<role>.json, written before the
//                    run by tools/auth/role_states.py (UIExecutionAgent with execution.role_auth: true, or
//                    `python -m tools.auth.role_states --project <name>`). Logging in there, outside the
//                    test runner, keeps credentials out of traces, videos and reports.
// A missing file or an undeclared role throws, naming the command that fixes it.

import fs from 'fs';
import path from 'path';

export type RoleStrategy = 'credentials' | 'storageState' | 'setup' | 'anonymous';
export interface RoleSpec {
  name: string;
  strategy: RoleStrategy;
  storage_state_path?: string;
}
export interface EmptyStorageState {
  cookies: never[];
  origins: never[];
}

const STRATEGIES: RoleStrategy[] = ['credentials', 'storageState', 'setup', 'anonymous'];

/** Role name -> file name; identical to tools/auth/role_states.py::role_file_name. */
export function roleFileName(role: string): string {
  const base = role.replace(/[^A-Za-z0-9_-]/g, '_').replace(/^_+|_+$/g, '');
  return `${base || 'role'}.json`;
}

/** project.yaml `auth.roles` -> {name: RoleSpec}. `anonymous: true` is shorthand; an unknown strategy
 * skips the role (as resolve_roles does). Read even when auth.enabled is false. */
export function rolesFromProject(project: Record<string, any> | null): Record<string, RoleSpec> {
  const roles = project?.auth?.roles;
  const out: Record<string, RoleSpec> = {};
  if (!roles || typeof roles !== 'object' || Array.isArray(roles)) return out;
  for (const [name, raw] of Object.entries(roles)) {
    const spec: Record<string, any> = raw && typeof raw === 'object' ? (raw as Record<string, any>) : {};
    const strategy: string = spec.anonymous ? 'anonymous' : spec.strategy ?? 'anonymous';
    if (!STRATEGIES.includes(strategy as RoleStrategy)) continue;
    out[name] = { name, strategy: strategy as RoleStrategy, storage_state_path: spec.storage_state_path };
  }
  return out;
}

export interface ResolveOptions {
  project: Record<string, any> | null;
  projectName: string | undefined;
  cwd?: string;
  exists?: (file: string) => boolean;
}

export function resolveRoleStorageState(role: string, opts: ResolveOptions): string | EmptyStorageState {
  const cwd = opts.cwd ?? process.cwd();
  const exists = opts.exists ?? fs.existsSync;
  const projectName = opts.projectName || '(PW_PROJECT unset)';
  const spec = rolesFromProject(opts.project)[role];
  if (!spec) {
    const known = Object.keys(rolesFromProject(opts.project));
    throw new Error(
      `role '${role}' is not declared in auth.roles of project '${projectName}'` +
        (known.length ? ` (declared: ${known.join(', ')})` : ' (no roles declared)'),
    );
  }
  if (spec.strategy === 'anonymous') return { cookies: [], origins: [] };
  if (spec.strategy === 'storageState') {
    const file = spec.storage_state_path ? path.resolve(cwd, spec.storage_state_path) : '';
    if (!file || !exists(file)) {
      throw new Error(
        `role '${role}': storage_state_path not found (${spec.storage_state_path ?? 'unset'}) — capture it first ` +
          `(python main.py --project ${projectName} --auth-setup)`,
      );
    }
    return file;
  }
  const file = path.join(cwd, 'application_assets', 'projects', opts.projectName ?? '', '.auth', roleFileName(role));
  if (!exists(file)) {
    throw new Error(
      `role '${role}': ${file} not found — log the role in first: ` +
        `python -m tools.auth.role_states --project ${projectName} (or set execution.role_auth: true)`,
    );
  }
  return file;
}
