// paint_guard.mjs: keep static pages compositing during browser video capture
// and identify a missed first paint when a dark scene unexpectedly starts white.
// Chromium screencast only emits a frame when something is repainted, so the
// keepalive must change a painted property, not a sub-pixel transform.

export const KEEPALIVE_JS = `
  (() => {
    const id = '__demo_paint_keepalive';
    let frame = 0;
    const paint = () => {
      const root = document.documentElement;
      if (root) {
        let pixel = document.getElementById(id);
        if (!pixel) {
          pixel = document.createElement('div');
          pixel.id = id;
          pixel.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;'
            + 'pointer-events:none;z-index:2147483647;';
          root.appendChild(pixel);
        }
        pixel.style.backgroundColor = (frame++ % 2)
          ? 'rgba(128,128,128,0.02)' : 'rgba(128,128,128,0.03)';
      }
      requestAnimationFrame(paint);
    };
    requestAnimationFrame(paint);
  })();
`;

export function hexLuma(hex) {
  if (typeof hex !== 'string') return null;
  const value = hex.trim();
  let rgb;
  if (/^#[\da-f]{3}$/i.test(value)) {
    rgb = [...value.slice(1)].map((c) => parseInt(c + c, 16));
  } else if (/^#[\da-f]{6}$/i.test(value)) {
    rgb = [0, 2, 4].map((i) => parseInt(value.slice(i + 1, i + 3), 16));
  } else {
    return null;
  }
  return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
}

export function isBlankWhite(yavg, bgHex) {
  const luma = hexLuma(bgHex);
  return luma !== null && luma < 100 && Number(yavg) > 200;
}
