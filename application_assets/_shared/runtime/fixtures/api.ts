// api.ts — the `api` fixture (Phase 4.4): a Playwright request context with the test's auth and base URL.
//
// storageState is the one the test's browser context starts with — the `role` option's state
// (auth/roles.ts::resolveRoleStorageState) or the config's PW_STORAGE_STATE — so `api` acts as the same user.
// Absolute URLs outside MTA_ALLOWED_HOSTS are refused (Phase 0 rail), exactly like page navigations.

import type { APIRequestContext } from '@playwright/test';
import { isUrlAllowed, SafetyError } from '../safety';

const GUARDED = new Set(['get', 'post', 'put', 'patch', 'delete', 'head', 'fetch']);

/** Wraps a request context so every call to an absolute URL outside `allowedHosts` throws a SafetyError. */
export function guardApi<T extends object = APIRequestContext>(ctx: T, allowedHosts: string[] | null, baseURL?: string): T {
  return new Proxy(ctx, {
    get(target, prop, receiver) {
      const value = Reflect.get(target, prop, receiver);
      if (typeof prop !== 'string' || !GUARDED.has(prop) || typeof value !== 'function') {
        return typeof value === 'function' ? value.bind(target) : value;
      }
      return (urlOrRequest: unknown, ...rest: unknown[]) => {
        if (typeof urlOrRequest === 'string' && !isUrlAllowed(urlOrRequest, allowedHosts, baseURL)) {
          throw new SafetyError(
            `api.${prop}('${urlOrRequest}') is outside safety.allowed_hosts [${(allowedHosts ?? []).join(', ')}]`,
          );
        }
        return (value as (...a: unknown[]) => unknown).call(target, urlOrRequest, ...rest);
      };
    },
  });
}
