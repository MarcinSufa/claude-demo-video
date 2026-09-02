// glow_check.mjs: selector validation shared by record-browser.mjs and its tests.
//
// A glow/highlight target must match exactly one DOM node, otherwise the pulse
// lands on the wrong element or nowhere, and the mistake only shows in the render.

export function glowTarget(action) {
  if (action.highlight) return action.highlight;
  if (!action.glow) return null;
  if (action.click) return action.click;
  if (action.hover) return action.hover;
  if (action.fill?.selector) return action.fill.selector;
  return null;
}

export function actionLabel(action) {
  if (action.label) return action.label;
  for (const kind of ['click', 'hover', 'fill', 'highlight']) {
    if (action[kind]) return kind;
  }
  return 'action';
}

export function selectorCountError(label, selector, count) {
  if (count === 1) return null;
  if (count === null || count === undefined) {
    return `glow target for "${label}" is not a valid DOM selector: ${selector} `
      + '(Playwright-only syntax such as ">> nth=0" or "text=" cannot be highlighted)';
  }
  return `glow target for "${label}" must match exactly one node: ${selector} matches ${count}`;
}
