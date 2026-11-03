import { describe, expect, it } from 'vitest';
import { scopeStyles } from '@/shell/styles';

/**
 * Scoping a plugin's CSS to its own screens: every rule ends up inside one
 * `@scope ([data-module="<slug>"])` block, whatever the text tried. That the scope then holds when
 * a browser matches elements is proved by the end-to-end test, in Chrome.
 */
function scoped(slug: string, css: string): { sheet: CSSStyleSheet; inner: string[] } {
  const sheet = scopeStyles(slug, css);
  const scope = sheet.cssRules[0] as CSSGroupingRule;
  return {
    sheet,
    inner: Array.from(scope.cssRules).map((rule) => rule.cssText.replace(/\s+/g, ' ')),
  };
}

describe('scopeStyles', () => {
  it('puts every rule inside the scope of the module slug', () => {
    const { sheet, inner } = scoped(
      'bulletin',
      '.panel { color: red } .screen-lede { font-style: italic }',
    );

    expect(sheet.cssRules).toHaveLength(1);
    expect(sheet.cssRules[0]?.constructor.name).toBe('CSSScopeRule');
    expect(sheet.cssRules[0]?.cssText).toMatch(/^@scope \(\[data-module="bulletin"\]\)/);
    expect(inner).toHaveLength(2);
    expect(inner[0]).toMatch(/^\.panel \{ ?color: red;? ?\}$/);
    expect(inner[1]).toMatch(/^\.screen-lede \{ ?font-style: italic;? ?\}$/);
  });

  it('cannot be escaped by closing the block in the text', () => {
    // Spliced into a template, this would end the scope and restyle the whole editor.
    const { sheet, inner } = scoped('bulletin', '.a { color: red } } body { display: none } .b {');

    // Parsed first, whatever survives the parse is a rule, and every rule is inside the scope.
    expect(sheet.cssRules).toHaveLength(1);
    expect(sheet.cssRules[0]?.constructor.name).toBe('CSSScopeRule');
    expect(inner[0]).toMatch(/^\.a /);
  });

  it('keeps media and supports blocks, scoped', () => {
    const { inner } = scoped('bulletin', '@media (max-width: 600px) { .panel { padding: 0 } }');

    expect(inner[0]).toMatch(/^@media/);
  });

  it('refuses @import, which would fetch a stylesheet from elsewhere', () => {
    expect(() =>
      scopeStyles('bulletin', '@import url("https://elsewhere.example/a.css");'),
    ).toThrow(/@import/);
  });

  it('refuses rules whose names are global whatever block they sit in', () => {
    expect(() =>
      scopeStyles('bulletin', '@font-face { font-family: X; src: url(x.woff2) }'),
    ).toThrow(/@font-face, which cannot be scoped/);
    expect(() => scopeStyles('bulletin', '@keyframes spin { to { rotate: 1turn } }')).toThrow(
      /@keyframes, which cannot be scoped/,
    );
  });
});
