/* ENVIRONMENT prototype — binds a sample payload to the graphical plate.
   Python's only job in the real system is to push this JSON; every visual
   decision below belongs to the page. */

const ICONS = "assets/icons/";
const VB_W = 1320;
const VB_H = 300;

const el = (id) => document.getElementById(id);

function smoothPath(points) {
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

function renderHero(data) {
  const now = data.now;
  el("place").textContent = data.place.name;
  const lat = data.place.lat, lon = data.place.lon;
  el("coords").textContent =
    `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}   ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;

  const stamp = new Date(data.observed_at);
  el("stamp").textContent = stamp.toLocaleString("en-GB", {
    weekday: "long", day: "numeric", month: "long",
  }) + " · " + stamp.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

  el("heroIcon").src = ICONS + now.icon + ".svg";
  el("temp").textContent = Math.round(now.temp);
  el("summary").textContent = now.summary;
  el("narrative").textContent =
    `Feels like ${Math.round(now.feels_like)}°  ·  ${now.narrative}`;
  el("high").textContent = Math.round(now.high) + "°";
  el("low").textContent = Math.round(now.low) + "°";

  el("sunline").textContent =
    `Sunrise ${data.sun.rise}   ·   Sunset ${data.sun.set}   ·   ${data.sun.day_length} of daylight`;
}

function renderRidge(data) {
  const hours = data.hourly;
  const temps = hours.map((h) => h.temp);
  const lo = Math.min(...temps);
  const hi = Math.max(...temps);
  const span = Math.max(1, hi - lo);

  // Leave headroom at the top so floating figures never touch the edge.
  const TOP = 92, BOTTOM = 262;
  const yFor = (t) => BOTTOM - ((t - lo) / span) * (BOTTOM - TOP);
  const xFor = (i) => (i / (hours.length - 1)) * VB_W;

  const pts = hours.map((h, i) => [xFor(i), yFor(h.temp)]);
  const ridge = smoothPath(pts) + ` L ${VB_W} ${VB_H} L 0 ${VB_H} Z`;
  el("ridgePath").setAttribute("d", ridge);
  el("ridgeGlow").setAttribute("d", ridge);

  // Precipitation sits behind as a shallower, cooler swell.
  const rainPts = hours.map((h, i) => [xFor(i), VB_H - (h.rain / 100) * 116]);
  el("rainPath").setAttribute("d",
    smoothPath(rainPts) + ` L ${VB_W} ${VB_H} L 0 ${VB_H} Z`);

  // Floating figures: the peak, the trough, and a couple of waypoints.
  const peak = temps.indexOf(hi);
  const trough = temps.indexOf(lo);
  const marks = new Set([0, peak, trough, 8, 16]);
  const marksEl = el("ridgeMarks");
  marksEl.innerHTML = "";
  [...marks].sort((a, b) => a - b).forEach((i, n) => {
    if (i < 0 || i >= hours.length) return;
    const span = document.createElement("span");
    const isKey = i === peak || i === trough;
    span.className = "mark" + (isKey ? "" : " dim");
    span.textContent = Math.round(hours[i].temp) + "°";
    span.style.left = ((xFor(i) / VB_W) * 100).toFixed(2) + "%";
    span.style.top = ((yFor(hours[i].temp) / VB_H) * 298 - 16).toFixed(0) + "px";
    span.style.animationDelay = (1.3 + n * 0.14).toFixed(2) + "s";
    marksEl.appendChild(span);
  });

  const hoursEl = el("ridgeHours");
  hoursEl.innerHTML = "";
  hours.forEach((h, i) => {
    if (i % 3 !== 0) return;
    const span = document.createElement("span");
    span.className = "hour" + (i === 0 ? " on" : "");
    span.textContent = i === 0 ? "NOW" : h.t;
    span.style.left = ((xFor(i) / VB_W) * 100).toFixed(2) + "%";
    hoursEl.appendChild(span);
  });

  // Park the light shaft over the current hour, clear of the left edge.
  document.querySelector(".nowshaft").style.left =
    Math.max(2.6, (xFor(0) / VB_W) * 100).toFixed(2) + "%";
}

function renderReadings(data) {
  const host = el("readings");
  host.innerHTML = "";
  data.readings.forEach((r) => {
    const item = document.createElement("div");
    item.className = "rd";
    item.innerHTML = `
      <img class="rd-icon" src="${ICONS}${r.icon}.svg" alt="">
      <div class="rd-value">
        <span class="rd-n">${r.value}</span>
        <span class="rd-u">${r.unit}</span>
      </div>
      <p class="rd-label">${r.label}</p>
      <p class="rd-note">${r.note}</p>`;
    host.appendChild(item);
  });
}

function renderOutlook(data) {
  const strip = el("strip");
  strip.innerHTML = "";
  data.outlook.forEach((d, i) => {
    const card = document.createElement("div");
    card.className = "card" + (i === 0 ? " today" : "");
    card.innerHTML = `
      <img class="shot" src="assets/img/${d.image}" alt="">
      <div class="shade"></div>
      <img class="card-icon" src="${ICONS}${d.icon}.svg" alt="">
      <div class="card-body">
        <p class="card-day">${d.day}</p>
        <div class="card-temps">
          <span class="card-hi">${Math.round(d.high)}°</span>
          <span class="card-lo">${Math.round(d.low)}°</span>
        </div>
        <p class="card-sum">${d.summary}</p>
      </div>`;
    strip.appendChild(card);
  });
}

async function boot() {
  const res = await fetch("data/sample.json");
  const data = await res.json();
  renderHero(data);
  renderRidge(data);
  renderReadings(data);
  renderOutlook(data);
  document.body.dataset.ready = "1";
}

boot();
