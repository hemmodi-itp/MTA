import { describe, expect, it, vi } from 'vitest';
import { ActionEngine } from './ActionEngine';

function makeEngine(goto: (url: string, opts: unknown) => Promise<void>, waitForLoadState?: any) {
  const page = { goto, waitForLoadState: waitForLoadState ?? vi.fn().mockResolvedValue(undefined) } as any;
  return new ActionEngine(page, {}, []);
}

describe('ActionEngine.navigate', () => {
  it('defaults to an empty relative reference, not "/"', async () => {
    // Regression test for the M04 bug: baseURL was correctly resolved to
    // https://aws.amazon.com/partners/, but every generated spec's bare
    // action.navigate() call still opened https://aws.amazon.com/ (the
    // origin root) because goto('/') discards a baseURL's own path per
    // WHATWG URL resolution — goto('') preserves it. Locked in below.
    const goto = vi.fn().mockResolvedValue(undefined);
    const engine = makeEngine(goto);

    await engine.navigate();

    expect(goto).toHaveBeenCalledWith('', { waitUntil: 'domcontentloaded' });
  });

  it('still navigates to an explicit relative url when one is given', async () => {
    const goto = vi.fn().mockResolvedValue(undefined);
    const engine = makeEngine(goto);

    await engine.navigate('/pricing');

    expect(goto).toHaveBeenCalledWith('/pricing', { waitUntil: 'domcontentloaded' });
  });

  it('does not throw when the page never reaches networkidle', async () => {
    // Regression test for the real BS_011 failure: a chat/streaming SPA that
    // never truly idles used to hang the whole navigate() call on
    // networkidle up to the 30s navigationTimeout. The bounded best-effort
    // wait must swallow this, not propagate it.
    const goto = vi.fn().mockResolvedValue(undefined);
    const waitForLoadState = vi.fn().mockRejectedValue(new Error('Timeout waiting for networkidle'));
    const engine = makeEngine(goto, waitForLoadState);

    await expect(engine.navigate()).resolves.toBeUndefined();
    expect(waitForLoadState).toHaveBeenCalledWith('networkidle', { timeout: 5_000 });
  });
});

function makeEngineWithLocator(locator: any, contextOverrides?: any) {
  const context = { waitForEvent: vi.fn().mockResolvedValue(null), ...contextOverrides };
  const page = { context: () => context } as any;
  const engine = new ActionEngine(page, { target_link: locator }, []);
  return { engine, context };
}

describe('ActionEngine.click — target="_blank" links', () => {
  it('clicks normally when the link has no target attribute', async () => {
    const click = vi.fn().mockResolvedValue(undefined);
    const getAttribute = vi.fn().mockResolvedValue(null);
    const { engine, context } = makeEngineWithLocator({ click, getAttribute });

    await engine.click('target_link');

    expect(click).toHaveBeenCalledTimes(1);
    expect(context.waitForEvent).not.toHaveBeenCalled();
  });

  it('waits for and closes a popup opened by a target="_blank" link', async () => {
    // Regression test for the real SC-002 failure: clicking an "Opens in a
    // new window" link left a popup open, and the *next* locator's click
    // then timed out waiting for actionability on the original page.
    const click = vi.fn().mockResolvedValue(undefined);
    const getAttribute = vi.fn().mockResolvedValue('_blank');
    const closePopup = vi.fn().mockResolvedValue(undefined);
    const waitForLoadState = vi.fn().mockResolvedValue(undefined);
    const popup = { waitForLoadState, close: closePopup };
    const { engine, context } = makeEngineWithLocator(
      { click, getAttribute },
      { waitForEvent: vi.fn().mockResolvedValue(popup) },
    );

    await engine.click('target_link');

    expect(click).toHaveBeenCalledTimes(1);
    expect(context.waitForEvent).toHaveBeenCalledWith('page', { timeout: 5_000 });
    expect(closePopup).toHaveBeenCalledTimes(1);
  });

  it('does not throw when no popup actually opens despite target="_blank"', async () => {
    const click = vi.fn().mockResolvedValue(undefined);
    const getAttribute = vi.fn().mockResolvedValue('_blank');
    const { engine } = makeEngineWithLocator({ click, getAttribute });

    await expect(engine.click('target_link')).resolves.toBeUndefined();
  });
});

describe('ActionEngine.uploadFile — missing fixture files', () => {
  it('throws an actionable error instead of a raw ENOENT when the fixture is missing', async () => {
    const setInputFiles = vi.fn();
    const page = {} as any;
    const engine = new ActionEngine(page, { upload: { setInputFiles } }, []);

    await expect(engine.uploadFile('upload', 'C:\\definitely-not-a-real-file.pdf'))
      .rejects.toThrow(/Upload fixture not found/);
    expect(setInputFiles).not.toHaveBeenCalled();
  });
});

describe('WHATWG URL resolution — pins the root-cause reasoning', () => {
  const base = 'https://aws.amazon.com/partners/';

  it('an empty relative reference resolves to the base URL unchanged', () => {
    expect(new URL('', base).href).toBe(base);
  });

  it('an absolute-path reference ("/") discards the base URL\'s own path', () => {
    expect(new URL('/', base).href).toBe('https://aws.amazon.com/');
  });
});
