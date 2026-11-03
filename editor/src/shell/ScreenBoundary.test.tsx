import { afterEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { ScreenBoundary } from '@/shell/ScreenBoundary';

/**
 * A screen that throws while rendering takes down its own screen and nothing else: the rail beside
 * it — here, a sibling — keeps rendering, and the screen can be tried again.
 */
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let container: HTMLElement | null = null;

function mount(element: React.ReactElement): HTMLElement {
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root?.render(element));
  return container;
}

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe('ScreenBoundary', () => {
  it('shows the failure in place of the screen, and leaves the rest of the page alone', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    function Broken(): never {
      throw new Error('the plugin read a field that is not there');
    }

    const page = mount(
      <div>
        <nav>The rail</nav>
        <ScreenBoundary label="Bulletin">
          <Broken />
        </ScreenBoundary>
      </div>,
    );

    expect(page.querySelector('nav')?.textContent).toBe('The rail');
    expect(page.querySelector('h1')?.textContent).toBe('Bulletin stopped working');
    expect(page.querySelector('[role="alert"]')?.textContent).toBe(
      'the plugin read a field that is not there',
    );
  });

  it('renders the screen again when asked to try again', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let fail = true;
    function Flaky() {
      if (fail) {
        throw new Error('not yet');
      }
      return <p>Working now</p>;
    }

    const page = mount(
      <ScreenBoundary label="Bulletin">
        <Flaky />
      </ScreenBoundary>,
    );
    fail = false;
    act(() => page.querySelector('button')?.click());

    expect(page.textContent).toBe('Working now');
  });

  it('renders a screen that works as if it were not there', () => {
    const page = mount(
      <ScreenBoundary label="Content">
        <p>Catalogue</p>
      </ScreenBoundary>,
    );

    expect(page.innerHTML).toBe('<p>Catalogue</p>');
  });
});
