import { describe, expect, it } from 'vitest';
import { CleanupRegistry } from './cleanup';

describe('cleanup registry', () => {
  it('runs entries in reverse order (newest first), API first', async () => {
    const order: string[] = [];
    const reg = new CleanupRegistry<string, string>();
    reg.register('product 1', { api: async () => { order.push('api:1'); } });
    reg.register('product 2', { api: async () => { order.push('api:2'); }, ui: async () => { order.push('ui:2'); } });
    reg.register('product 3', { ui: async () => { order.push('ui:3'); } });
    const out = await reg.run({ api: () => 'API', page: () => 'PAGE' });
    expect(order).toEqual(['ui:3', 'api:2', 'api:1']);
    expect(out.failures).toEqual([]);
    expect(out.done.map((d) => `${d.label}/${d.via}`)).toEqual(['product 3/ui', 'product 2/api', 'product 1/api']);
    expect(reg.size).toBe(0);
  });

  it('falls back to the UI handler when the API handler throws', async () => {
    const reg = new CleanupRegistry();
    reg.register('order 9', { api: async () => { throw new Error('405 Method Not Allowed'); }, ui: async () => {} });
    const out = await reg.run({ api: () => 'api', page: () => 'page' });
    expect(out.done).toEqual([{ label: 'order 9', via: 'ui' }]);
    expect(out.failures).toEqual([]);
  });

  it('reports every failure — never swallows — and still runs the other entries', async () => {
    const ran: string[] = [];
    const reg = new CleanupRegistry();
    reg.register('a', { api: async () => { ran.push('a'); } });
    reg.register('b', { api: async () => { throw new Error('500 boom\nstack…'); }, ui: async () => { throw new Error('button gone'); } });
    reg.register('c', { api: async () => { throw new Error('\x1b[31m404\x1b[0m'); } });
    const out = await reg.run({ api: () => 'api', page: () => 'page' });
    expect(ran).toEqual(['a']);
    expect(out.failures).toEqual([
      { label: 'c', via: 'api', error: '404' },
      { label: 'b', via: 'ui', error: 'api: 500 boom; ui: button gone' },
    ]);
  });

  it('an entry with no usable context is a failure, not a silent skip', async () => {
    const reg = new CleanupRegistry();
    reg.register('x', { ui: async () => {} });
    const out = await reg.run({ api: () => 'api' });
    expect(out.failures).toEqual([{ label: 'x', via: 'none', error: 'no usable handler (api/ui context unavailable)' }]);
  });

  it('register needs a handler', () => {
    expect(() => new CleanupRegistry().register('x', {})).toThrow(/api and\/or a ui handler/);
  });

  it('the api context is only requested when a task needs it', async () => {
    let made = 0;
    const reg = new CleanupRegistry();
    reg.register('ui only', { ui: async () => {} });
    await reg.run({ api: () => { made += 1; return 'api'; }, page: () => 'page' });
    expect(made).toBe(0);
  });
});
