/**
 * A module's `styles`, scoped to its own screens.
 *
 * Every screen renders inside `<div data-module="<slug>">` (see `ModuleOutlet`). The module's CSS
 * is parsed by the browser into rules, and each rule is inserted into one
 * `@scope ([data-module="<slug>"])` block, so a selector such as `.panel` matches the module's own
 * panels and no other module's. Parsing first and inserting rule by rule is what makes the scope
 * hold: text spliced into a template could close the block early (`} body { … }`) and escape it.
 *
 * Rules that cannot be scoped are refused, and the module with them: `@import` fetches another
 * sheet, and `@font-face`, `@keyframes`, `@property` and `@layer` statements define names that are
 * global whatever block they sit in. A browser without CSS `@scope` refuses every plugin style
 * rather than applying it unscoped.
 *
 * This keeps one plugin from restyling another by accident. It is not a security boundary: a
 * plugin's script runs on this page and could add a stylesheet of its own.
 */
const SCOPABLE = ['CSSStyleRule', 'CSSMediaRule', 'CSSSupportsRule', 'CSSContainerRule'];

function kindOf(rule: CSSRule): string {
  return rule.constructor.name;
}

export function scopeStyles(slug: string, css: string): CSSStyleSheet {
  if (/@import\b/i.test(css)) {
    throw new Error('its styles use @import, which would fetch a stylesheet from elsewhere');
  }
  const parsed = new CSSStyleSheet();
  parsed.replaceSync(css);

  const scoped = new CSSStyleSheet();
  // The slug has already passed the registry's check: lowercase letters, digits, - and _.
  scoped.replaceSync(`@scope ([data-module="${slug}"]) {}`);
  const scope = scoped.cssRules[0];
  if (!scope || kindOf(scope) !== 'CSSScopeRule') {
    throw new Error(
      "this browser cannot scope a plugin's styles (CSS @scope), so none are applied",
    );
  }
  const block = scope as CSSGroupingRule;
  for (const rule of Array.from(parsed.cssRules)) {
    if (!SCOPABLE.includes(kindOf(rule))) {
      const name = /^@[a-z-]+/i.exec(rule.cssText)?.[0] ?? kindOf(rule);
      throw new Error(`its styles use ${name}, which cannot be scoped to one module`);
    }
    block.insertRule(rule.cssText, block.cssRules.length);
  }
  return scoped;
}
