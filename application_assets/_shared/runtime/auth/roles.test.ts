import path from 'path';
import { describe, expect, it } from 'vitest';

import { resolveRoleStorageState, roleFileName, rolesFromProject } from './roles';

const PROJECT = {
  auth: {
    enabled: false,
    roles: {
      admin: { strategy: 'credentials', login_url: 'http://x/login', username_env: 'A_USER', password_env: 'A_PASS' },
      user: { strategy: 'setup', steps: [{ goto: 'http://x/login' }] },
      saved: { strategy: 'storageState', storage_state_path: '.auth/saved.json' },
      guest: { anonymous: true },
      weird: { strategy: 'magic' },
    },
  },
};
const CWD = path.resolve('/repo');

describe('roleFileName (same rule as role_states.py::role_file_name)', () => {
  it('sanitises names', () => {
    expect(roleFileName('admin')).toBe('admin.json');
    expect(roleFileName('Sales Manager/EU')).toBe('Sales_Manager_EU.json');
    expect(roleFileName('__')).toBe('role.json');
  });
});

describe('rolesFromProject', () => {
  it('reads auth.roles; anonymous shorthand; unknown strategy skipped', () => {
    const roles = rolesFromProject(PROJECT);
    expect(Object.keys(roles)).toEqual(['admin', 'user', 'saved', 'guest']);
    expect(roles.guest.strategy).toBe('anonymous');
    expect(rolesFromProject(null)).toEqual({});
    expect(rolesFromProject({ auth: { roles: ['x'] } })).toEqual({});
  });
});

describe('resolveRoleStorageState', () => {
  const opts = (exists: (f: string) => boolean) => ({ project: PROJECT, projectName: 'shop', cwd: CWD, exists });

  it('anonymous -> empty storage state, no file needed', () => {
    expect(resolveRoleStorageState('guest', opts(() => false))).toEqual({ cookies: [], origins: [] });
  });

  it('credentials / setup -> .auth/<role>.json of the project', () => {
    const expected = path.join(CWD, 'application_assets', 'projects', 'shop', '.auth', 'admin.json');
    expect(resolveRoleStorageState('admin', opts((f) => f === expected))).toBe(expected);
    const user = path.join(CWD, 'application_assets', 'projects', 'shop', '.auth', 'user.json');
    expect(resolveRoleStorageState('user', opts((f) => f === user))).toBe(user);
  });

  it('storageState -> its own path, resolved against cwd', () => {
    const expected = path.resolve(CWD, '.auth/saved.json');
    expect(resolveRoleStorageState('saved', opts((f) => f === expected))).toBe(expected);
  });

  it('missing file -> error naming the command to run', () => {
    expect(() => resolveRoleStorageState('admin', opts(() => false))).toThrow(/python -m tools\.auth\.role_states --project shop/);
    expect(() => resolveRoleStorageState('saved', opts(() => false))).toThrow(/--auth-setup/);
  });

  it('undeclared role -> error listing the declared roles', () => {
    expect(() => resolveRoleStorageState('root', opts(() => true))).toThrow(/not declared.*admin, user, saved, guest/);
    expect(() => resolveRoleStorageState('root', { project: null, projectName: 'shop', cwd: CWD, exists: () => true }))
      .toThrow(/no roles declared/);
  });
});
