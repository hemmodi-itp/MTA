import { describe, expect, it, vi } from 'vitest';
import { guardApi } from './api';
import { resolveRoleStorageState } from '../auth/roles';

function fakeCtx() {
  return {
    get: vi.fn().mockResolvedValue('got'),
    post: vi.fn().mockResolvedValue('posted'),
    fetch: vi.fn().mockResolvedValue('fetched'),
    dispose: vi.fn(),
    storageState: vi.fn().mockResolvedValue({ cookies: [] }),
  };
}

describe('api fixture — host guard', () => {
  it('relative URLs resolve against the baseURL and pass', async () => {
    const ctx = fakeCtx();
    const api = guardApi(ctx, ['127.0.0.1'], 'http://127.0.0.1:8765');
    await expect(api.get('/api/products')).resolves.toBe('got');
    expect(ctx.get).toHaveBeenCalledWith('/api/products');
  });

  it('an absolute URL on an allowed host passes, any other host is refused', async () => {
    const ctx = fakeCtx();
    const api = guardApi(ctx, ['127.0.0.1'], 'http://127.0.0.1:8765');
    await expect(api.post('http://127.0.0.1:8765/products/1/delete', { form: {} })).resolves.toBe('posted');
    expect(() => api.fetch('https://evil.example/steal')).toThrow(/outside safety.allowed_hosts/);
    expect(ctx.fetch).not.toHaveBeenCalled();
  });

  it('no allow-list (hand run) -> not enforced; other members pass through', async () => {
    const ctx = fakeCtx();
    const api = guardApi(ctx, null);
    await expect(api.get('https://anywhere.example/')).resolves.toBe('got');
    await api.storageState();
    api.dispose();
    expect(ctx.dispose).toHaveBeenCalled();
  });
});

describe('api fixture — role auth (shared with the role option)', () => {
  const project = {
    auth: { roles: { admin: { strategy: 'setup' }, guest: { anonymous: true }, svc: { strategy: 'storageState', storage_state_path: 's.json' } } },
  };
  it('a logged-in role -> its .auth/<role>.json', () => {
    const p = resolveRoleStorageState('admin', { project, projectName: 'p', cwd: '/r', exists: () => true });
    expect(String(p).replace(/\\/g, '/')).toBe('/r/application_assets/projects/p/.auth/admin.json');
  });
  it('anonymous -> an empty state', () => {
    expect(resolveRoleStorageState('guest', { project, projectName: 'p' })).toEqual({ cookies: [], origins: [] });
  });
});
