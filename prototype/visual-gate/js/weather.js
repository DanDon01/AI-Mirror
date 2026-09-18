/* Weather: a temperature, an atmospheric object, a day curve.
   Nothing else unless something becomes contextually important. */

window.Weather = (function () {
  const VB_W = 1200, VB_H = 150;

  function smooth(points) {
    let d = `M ${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i - 1] || points[i];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[i + 2] || p2;
      const c1x = p1[0] + (p2[0] - p0[0]) / 6;
      const c1y = p1[1] + (p2[1] - p0[1]) / 6;
      const c2x = p2[0] - (p3[0] - p1[0]) / 6;
      const c2y = p2[1] - (p3[1] - p1[1]) / 6;
      d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
    }
    return d;
  }

  function mount(data) {
    document.querySelector('#temp .temp-n').textContent =
      Math.round(data.temperature_c);

    const series = data.hourly_c || [];
    if (series.length < 2) {
      document.getElementById('curve').style.display = 'none';
    } else {
      const lo = Math.min(...series), hi = Math.max(...series);
      const span = Math.max(1, hi - lo);
      const pts = series.map((v, i) => [
        (i / (series.length - 1)) * VB_W,
        VB_H - 26 - ((v - lo) / span) * (VB_H - 62),
      ]);
      const line = smooth(pts);
      document.getElementById('curveLine').setAttribute('d', line);
      document.getElementById('curveGlow').setAttribute('d', line);
      document.getElementById('curveArea').setAttribute(
        'd', line + ` L ${VB_W} ${VB_H} L 0 ${VB_H} Z`);
    }

    buildRain(46);
  }

  function buildRain(n) {
    const host = document.getElementById('rainfall');
    if (host.childElementCount) return;
    let html = '';
    for (let i = 0; i < n; i++) {
      // Deterministic placement so captures are reproducible.
      const r = ((Math.sin(i * 78.233) * 43758.5453) % 1 + 1) % 1;
      const r2 = ((Math.sin(i * 12.9898) * 24634.6345) % 1 + 1) % 1;
      const dur = (0.85 + r2 * 0.5).toFixed(2);
      html += `<i style="left:${(r * 100).toFixed(2)}%;`
           + `animation-duration:${dur}s;`
           + `animation-delay:-${(r2 * 1.4).toFixed(2)}s;`
           + `opacity:${(0.35 + r2 * 0.65).toFixed(2)}"></i>`;
    }
    host.innerHTML = html;
  }

  /** The reactive state, driven by an explicit 0..1 progress: the cloud
      darkens, rain falls, and one minimal readout emerges. */
  function setAlert(p, value) {
    p = Math.max(0, Math.min(1, p || 0));
    const box = document.getElementById('walert');
    const rain = document.getElementById('rainfall');
    const sky = document.querySelector('.sky');

    if (value) document.getElementById('walertV').textContent = value;
    box.style.opacity = p.toFixed(3);
    box.style.transform = `translate3d(0, ${((1 - p) * 18).toFixed(1)}px, 0)`;
    rain.style.opacity = (p * 0.5).toFixed(3);
    sky.style.filter = p > 0.001
      ? `brightness(${(1 - p * 0.38).toFixed(3)}) saturate(${(1 - p * 0.2).toFixed(3)})`
      : '';
  }

  return { mount, setAlert };
})();
