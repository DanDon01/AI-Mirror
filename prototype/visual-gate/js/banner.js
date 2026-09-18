/* The event banner: the house receiving something.

   A hairline of light grows out of the right edge of the glass, opens
   into a translucent pane, presents one line, then folds back into the
   edge and leaves the mirror clean.

   Driven by an explicit 0..1 progress rather than CSS transitions, so a
   frame can be reproduced exactly at any point in the motion. */

window.Banner = (function () {
  let root, glass, inner, armed = false;

  const ramp = (x, a, b) => {
    const v = Math.max(0, Math.min(1, (x - a) / (b - a)));
    return v * v * (3 - 2 * v);
  };

  function mount(event) {
    root = document.getElementById('banner');
    glass = root.querySelector('.banner-glass');
    inner = root.querySelector('.banner-inner');
    if (!event) return;
    document.getElementById('bSrc').textContent = event.source;
    document.getElementById('bHead').textContent = event.headline;
    document.getElementById('bWhen').textContent = event.time;
    armed = true;
  }

  /** p: 0 retracted into the edge, 1 fully open. */
  function setProgress(p) {
    if (!armed) return;
    p = Math.max(0, Math.min(1, p));
    root.style.opacity = p > 0.001 ? '1' : '0';

    // The line reaches across first, then the pane opens vertically.
    const reach = ramp(p, 0.0, 0.58);
    const open = ramp(p, 0.34, 0.86);
    glass.style.transform =
      `scaleX(${(0.002 + reach * 0.998).toFixed(4)}) ` +
      `scaleY(${(0.02 + open * 0.98).toFixed(4)})`;

    const content = ramp(p, 0.62, 1.0);
    inner.style.opacity = content.toFixed(3);
    inner.style.transform = `translate3d(${((1 - content) * 26).toFixed(1)}px,0,0)`;
  }

  return { mount, setProgress };
})();
