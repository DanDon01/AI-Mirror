/* The home is drawn from fixed architectural coordinates. All changing
   values arrive from the existing bridge; this file never fetches HA. */
const HomeTwin = (() => {
  'use strict';
  const W = 2.5, D = 1.65, H = 1.65, FLOOR = .82, RIDGE = 2.23;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const num = v => typeof v === 'number' && Number.isFinite(v);
  // Fit to the real panel band with room BELOW for household consumption.
  const point = ([x,y,z]) => [300 + (z-x)*76, 184 + (x+z)*23 - y*76];
  const pts = a => a.map(p=>point(p).map(v=>v.toFixed(2)).join(',')).join(' ');
  const poly = (p, c, extra='') => `<polygon class="${c}" points="${pts(p)}" ${extra}/>`;
  const line = (a,b,c) => `<polyline class="${c}" points="${pts([a,b])}"/>`;
  const front = (x0,x1,y0,y1,z=D) => [[x0,y0,z],[x1,y0,z],[x1,y1,z],[x0,y1,z]];
  const side = (x,z0,z1,y0,y1) => [[x,y0,z0],[x,y0,z1],[x,y1,z1],[x,y1,z0]];
  const box = (x0,x1,z0,z1,y0,y1,c) =>
    poly(side(x1,z0,z1,y0,y1),c+' side') + poly(front(x0,x1,y0,y1,z1),c+' front') +
    poly([[x0,y1,z0],[x1,y1,z0],[x1,y1,z1],[x0,y1,z1]],c+' top');
  const dot = (p,r,c) => {const [x,y]=point(p);return `<circle class="${c}" cx="${x}" cy="${y}" r="${r}"/>`;};
  const roof = (x,u) => [x,H+(RIDGE-H)*u,D-u*D/2];
  const rgb = watts => { const t=clamp((watts||0)/3000,0,1); return `${Math.round(33+210*t)},${Math.round(60+140*t)},${Math.round(86-22*t)}`; };
  let state={}, curtain=1, target=1, last=0, changedAt=-100, received=-Infinity;
  const previousMotion={}, motionStarted={}, presenceLevel={};
  let thermalStarted=-100, thermalSignature='';
  function update(data, now=performance.now()/1000) {
    state=data || {};
    received=now;
    const room=(state.rooms||{}).livingroom||{};
    let next=num(room.curtain_position) ? clamp(room.curtain_position/100,0,1) :
      room.curtain==='closed' ? 0 : room.curtain==='open' ? 1 : null;
    if(next!==null) {
      if(!last) curtain=next;
      if(next!==target) changedAt=now;
      target=next;
    }
    for(const area of ['livingroom','bedroom','porch','external']) {
      const active=((state.rooms||{})[area]||{}).occupied===true;
      if(active && !previousMotion[area]) motionStarted[area]=now;
      previousMotion[area]=active;
    }
    const sig=JSON.stringify(['downstairs','upstairs'].map(k=>((state.rooms||{})[k]||{}).temperature_c));
    if(sig!==thermalSignature) { thermalStarted=now; thermalSignature=sig; }
  }
  function car(charging) {
    // Lofted body sections: shaped bonnet, boot, shoulder and wheel arches.
    const z0=1.99,z1=2.48,x0=.12,x1=1.44;
    const sections=[[x0,.14,.20],[.25,.24,.245],[.48,.26,.25],[1.10,.25,.245],[1.33,.20,.22],[x1,.13,.17]];
    let s='<g class="t-car'+(charging===true?' charging':'')+'">';
    for(let j=0;j<2;j++) for(const x of [.39,1.17]) {
      // All four tyres are full curved discs in the wheel plane, with hubs.
      const z=j?z1+.012:z0-.012;
      const ring=Array.from({length:24},(_,i)=>[x+.105*Math.cos(i*Math.PI/12),.105+.105*Math.sin(i*Math.PI/12),z]);
      s+=poly(ring,'tyre')+dot([x,.105,z],2.4,'hub');
    }
    for(let i=0;i<sections.length-1;i++) {
      const a=sections[i],b=sections[i+1];
      s+=poly([[a[0],a[1],z0],[b[0],b[1],z0],[b[0],b[2],z1],[a[0],a[2],z1]],'coach top');
    }
    const flank=[[x0,.10,z1],[.24,.085,z1]];
    for(const x of [.39,1.17]) {
      for(let i=0;i<=12;i++) {const a=Math.PI-i*Math.PI/12;flank.push([x+.119*Math.cos(a),.105+.119*Math.sin(a),z1]);}
    }
    flank.push([x1,.1,z1],[x1,.17,z1],[1.33,.22,z1],[1.1,.245,z1],[.48,.25,z1],[.25,.245,z1],[x0,.20,z1]);
    s+=poly(flank,'coach front');
    s+=poly(side(x1,z0,z1,.10,.17),'coach side');
    const cabinSide=[[.45,.25,z1-.025],[1.1,.245,z1-.025],[.93,.43,z1-.09],[.61,.43,z1-.09]];
    s+=poly(cabinSide,'vehicle-glass');
    s+=poly([[.61,.43,z0+.09],[.93,.43,z0+.09],[.93,.43,z1-.09],[.61,.43,z1-.09]],'coach roof');
    s+=poly([[.93,.43,z0+.09],[1.1,.25,z0+.025],[1.1,.245,z1-.025],[.93,.43,z1-.09]],'vehicle-glass');
    s+=line([.78,.43,z1-.09],[.78,.25,z1-.025],'pillar');
    s+=line([.80,.24,z1+.01],[.80,.13,z1+.01],'door-seam');
    s+=line([.86,.225,z1+.014],[.94,.225,z1+.014],'handle');
    s+=line([x1,.165,z0+.05],[x1,.165,z0+.16],'headlamp');
    s+=line([x1,.165,z1-.16],[x1,.165,z1-.05],'headlamp');
    s+=line([x0,.17,z1-.10],[x0,.17,z1],'tail-lamp');
    return s+'</g>';
  }
  function windowPanel(p, lit, curtains=false) {
    let s=poly(p,lit===true?'window lit':'window');
    if(curtains) {
      const width=(p[1][0]-p[0][0])*(.5-.46*curtain);
      const x0=p[0][0],x1=p[1][0],y0=p[0][1],y1=p[2][1];
      s+=poly(front(x0,x0+width,y0,y1,D+.002),'fabric');
      s+=poly(front(x1-width,x1,y0,y1,D+.002),'fabric');
      for(let i=1;i<4;i++) {
        s+=line([x0+width*i/4,y0,D+.003],[x0+width*i/4,y1,D+.003],'pleat');
        s+=line([x1-width*i/4,y0,D+.003],[x1-width*i/4,y1,D+.003],'pleat');
      }
    }
    s+=poly(p,'window-frame');
    const mid=(p[0][0]+p[1][0])/2;
    if(p[0][0]!==p[1][0])s+=line([mid,p[0][1],p[0][2]],[mid,p[2][1],p[2][2]],'mullion');
    return s;
  }
  function presence(p, level) {
    if(level<.01)return '';
    const [x,y]=point(p);
    return `<g class="presence" opacity="${level}" transform="translate(${x},${y})"><ellipse cy="1" rx="11" ry="3"/><circle cy="-28" r="3.5"/><path d="M-7-6 Q-7-23 0-23 Q7-23 7-6 M-3-8 -4 0 M3-8 4 0"/><circle cx="-10" cy="-13" r=".7"/><circle cx="9" cy="-20" r=".8"/></g>`;
  }
  function render(now=performance.now()/1000) {
    if(now-received>30) {
      state={};
      for(const area of Object.keys(previousMotion)) previousMotion[area]=false;
    }
    const dt=last?clamp(now-last,0,.1):0;last=now;
    curtain+=(target-curtain)*(1-Math.exp(-dt*2.5));
    for(const area of ['livingroom','bedroom','porch','external']) {
      const goal=previousMotion[area] ? .75+.25*Math.sin(now*2) : 0;
      presenceLevel[area]=(presenceLevel[area]||0)+(goal-(presenceLevel[area]||0))*(1-Math.exp(-dt*2));
    }
    const rooms=state.rooms||{}, living=rooms.livingroom||{}, bedroom=rooms.bedroom||{};
    const pulse = area => previousMotion[area] && now-(motionStarted[area]||0)<8;
    let s='<svg class="home-twin" viewBox="0 0 580 365" aria-label="Live miniature home">';
    // The driveway is a real architectural boundary, always present.
    s+=poly([[0,0,D],[3.27,0,D],[3.27,0,2.75],[0,0,2.75]],'drive-outline');
    // Opaque faces remove phantom rear edges and the old decorative green band.
    s+=poly(side(W,0,D,0,H),'wall side')+poly(front(0,W,0,H),'wall front');
    s+=line([W,FLOOR,0],[W,FLOOR,D],'floor-joint')+line([0,FLOOR,D],[W,FLOOR,D],'floor-joint');
    s+=windowPanel(front(.18,1.02,1.02,1.46),bedroom.light);
    s+=windowPanel(front(1.42,2.06,1.02,1.46),(rooms.upstairs||{}).light);
    s+=windowPanel(side(W,.35,1,1.02,1.46),(rooms.upstairs||{}).light);
    const emphasis=Math.max(0,1-(now-changedAt)/4);
    s+='<g style="filter:'+(emphasis>0?'drop-shadow(0 0 '+(emphasis*2)+'px #98aeb7)':'none')+'">';
    const curtainKnown=num(living.curtain_position)||['open','closed'].includes(living.curtain);
    s+=windowPanel(front(.17,1.19,.28,.70),living.light,curtainKnown)+'</g>';
    // Main front roof and hipped left end. Fixed coordinates, no floating array.
    s+=poly([[0,H,D],[W,H,D],[1.96,RIDGE,D/2],[0,RIDGE,D/2]],'roof-plane');
    s+=poly([[W,H,0],[W,H,D],[1.96,RIDGE,D/2]],'roof-hip');
    // Chimney at ridge; array BELOW it on the same roof plane. x footprint
    // overlaps chimney intentionally in plan, but u <= .66 is safely downslope.
    const pvRgb=rgb(state.solar_watts);
    for(let r=0;r<2;r++)for(let c=0;c<4;c++) {
      const x0=.16+c*.29,x1=x0+.26,u0=.16+r*.26,u1=u0+.24;
      s+=poly([roof(x0,u0),roof(x1,u0),roof(x1,u1),roof(x0,u1)],'solar-panel',`style="fill:rgb(${pvRgb})"`);
      for(let n=1;n<3;n++)s+=line(roof(x0+(x1-x0)*n/3,u0),roof(x0+(x1-x0)*n/3,u1),'solar-cell');
      s+=line(roof(x0,(u0+u1)/2),roof(x1,(u0+u1)/2),'solar-cell');
    }
    s+=box(.32,.57,.72,.91,2.12,2.58,'chimney');
    // Garage shares exactly x=W with the house; no shared face is drawn.
    // Its front extends forward of the main facade and hides that corner.
    s+=poly(side(3.27,.20,1.87,0,.71),'garage side');
    s+=poly(front(W,3.27,0,.71,1.87),'garage front');
    s+=poly([[W,.89,.20],[3.27,.71,.20],[3.27,.71,1.87],[W,.89,1.87]],'garage-roof');
    s+=poly(front(2.59,3.18,.05,.61,1.871),'garage-door');
    for(let y=.15;y<.61;y+=.10)s+=line([2.6,y,1.874],[3.17,y,1.874],'garage-slat');
    // Narrow projecting porch, with a human-sized door and handle.
    s+=box(1.66,2.20,D,1.97,0,.72,'porch');
    s+=poly([[1.62,.84,D],[2.24,.84,D],[2.24,.75,2.01],[1.62,.75,2.01]],'porch-roof');
    s+=poly(front(1.76,2.10,.035,.65,1.973),'entrance');
    s+=poly(front(1.80,2.06,.36,.60,1.976),'door-glass');
    s+=line([1.80,.27,1.978],[1.80,.34,1.978],'handle');
    // Tiny real-world device housings. Events require actual mapped HA data.
    s+=poly(front(2.13,2.18,.38,.50,1.978),'doorbell');
    s+=dot([2.155,.465,1.983],1.4,'lens'+(pulse('porch')?' awake':''));
    s+=line([2.24,.97,D],[2.31,.97,1.77],'camera-bracket');
    s+=box(2.23,2.36,1.75,1.84,.92,.99,'camera');
    s+=dot([2.30,.955,1.846],1.7,'lens'+(pulse('external')?' awake':''));
    // Presence is deliberately fuzzy and anchored to an area, never to a
    // claimed person coordinate. Occupancy never turns on window lights.
    s+=presence([.71,.28,1.655],presenceLevel.livingroom);
    s+=presence([.60,1.04,1.655],presenceLevel.bedroom);
    s+=presence([2.06,0,2.24],presenceLevel.porch);
    s+=presence([2.73,0,2.18],presenceLevel.external);
    s+=car((state.car||{}).charging);
    const soc=(state.car||{}).charge_pct;
    if(num(soc)) {
      // Screen-space offset below the lowest wheel, outside the car silhouette.
      const carBottom=point([1.44,0,2.48]);
      const x=carBottom[0]+8,y=carBottom[1]+19;
      s+=`<g class="battery-caption" transform="translate(${x},${y})"><rect x="0" y="-10" width="15" height="8" rx="1"/><path d="M15-8h2v4h-2"/><rect class="battery-level" x="2" y="-8" width="${clamp(soc,0,100)*.11}" height="4"/><text x="23" y="0">${Math.round(soc)}%</text></g>`;
    }
    // Temperature numbers sit just outside the right edge at each floor's
    // projected height, staggered in time. No permanently coloured floor.
    const phase=(now-thermalStarted)%144;
    for(const [key,y,start] of [['downstairs',.42,0],['upstairs',1.26,4]]) {
      const v=(rooms[key]||{}).temperature_c;
      if(!num(v))continue;
      const age=phase-start, a=age>=0&&age<7 ? Math.min(1,age,7-age)*.85:0;
      const q=point([0,y,D]);
      s+=`<g class="temperature" opacity="${a}"><path d="M${q[0]+4} ${q[1]}h10"/><text x="${q[0]+19}" y="${q[1]+7}">${v.toFixed(1)}°</text></g>`;
    }
    if(state.battery && num(state.battery.charge_pct)) {
      const b=state.battery,q=point([W,.40,.30]);
      s+=`<g class="home-battery ${b.charging===true?'active':''}" transform="translate(${q[0]},${q[1]})"><rect width="10" height="19" rx="2"/><rect x="2" y="${17-clamp(b.charge_pct,0,100)*.14}" width="6" height="${clamp(b.charge_pct,0,100)*.14}"/></g>`;
    }
    return s+'</svg>';
  }
  function mount(el) { let stamp=-1; return now=>{if(now-stamp>=1/24||now<stamp){el.innerHTML=render(now);stamp=now;}}; }
  return {update, render, mount};
})();
