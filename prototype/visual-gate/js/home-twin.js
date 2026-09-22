/* Live house renderer. Geometry is the existing house, now drawn natively in
   Three.js; HA data arrives through the existing bridge and is never fetched here. */
const HomeTwin = (() => {
  'use strict';
  const W=2.5,D=1.65,H=1.65,RIDGE=2.23;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  let state={}, received=-Infinity, eventEnergy=0, lastWatts=null;

  function update(data, now=performance.now()/1000) {
    state=data||{}; received=now;
    const watts=Number(state.watts_now);
    if(num(watts) && num(lastWatts)) eventEnergy=Math.max(eventEnergy,Math.min(1,Math.abs(watts-lastWatts)/180));
    if(num(watts))lastWatts=watts;
  }
  function quad(a,b,c,d,material) {
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.Float32BufferAttribute([...a,...b,...c,...d],3));
    g.setIndex([0,1,2,0,2,3]);g.computeVertexNormals();
    return new THREE.Mesh(g,material);
  }
  function glowTexture() {
    const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d');
    const g=x.createRadialGradient(32,32,0,32,32,32);g.addColorStop(0,'rgba(255,255,255,1)');g.addColorStop(.18,'rgba(180,238,255,.9)');g.addColorStop(1,'rgba(80,190,255,0)');x.fillStyle=g;x.fillRect(0,0,64,64);
    return new THREE.CanvasTexture(c);
  }
  // A low-poly trapezoid gives the car a proper glazed cabin silhouette without
  // spending Pi GPU time on a downloaded mesh.
  function taperedCabin(material) {
    const g=new THREE.BufferGeometry();
    const p=[-.36,0,-.23,.36,0,-.23,.36,0,.23,-.36,0,.23,-.23,.25,-.17,.21,.25,-.17,.21,.25,.17,-.23,.25,.17];
    g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));
    g.setIndex([0,1,2,0,2,3,4,6,5,4,7,6,0,4,5,0,5,1,1,5,6,1,6,2,2,6,7,2,7,3,3,7,4,3,4,0]);g.computeVertexNormals();
    return new THREE.Mesh(g,material);
  }
  function buildScene(el) {
    // Larger than the old SVG frame, with a slightly wider camera view.  The
    // twin needs breathing room for its slow parallax rather than clipping at
    // the edge of the energy panel.
    const canvas=document.createElement('canvas');canvas.className='home-twin-webgl';canvas.width=660;canvas.height=410;el.textContent='';el.appendChild(canvas);
    const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'high-performance'});
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.35));renderer.setSize(660,410,false);renderer.setClearColor(0x000000,0);
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.88;renderer.outputEncoding=THREE.sRGBEncoding;
    const scene=new THREE.Scene();
    // View from the real home's left-front side: garage and porch lead.
    const camera=new THREE.PerspectiveCamera(35,660/410,.1,30);camera.position.set(-5.1,3.35,5.4);camera.lookAt(1.55,.9,.95);
    const home=new THREE.Group();scene.add(home);
    // A deliberately transparent shell: this is a live holographic scan, not
    // a miniature physical house.  depthWrite is off so floor volumes remain
    // legible through the smoked outer skin.
    const steel=new THREE.MeshPhysicalMaterial({color:0x142936,emissive:0x062132,emissiveIntensity:.3,metalness:.38,roughness:.42,transparent:true,opacity:.25,depthWrite:false,side:THREE.DoubleSide});
    const wallInset=new THREE.MeshStandardMaterial({color:0x061017,emissive:0x082b42,emissiveIntensity:.18,transparent:true,opacity:.28,depthWrite:false,side:THREE.DoubleSide});
    const roofMat=new THREE.MeshPhysicalMaterial({color:0x162c3a,emissive:0x08263a,emissiveIntensity:.2,metalness:.26,roughness:.55,transparent:true,opacity:.34,depthWrite:false,side:THREE.DoubleSide});
    const edge=new THREE.LineBasicMaterial({color:0x4d9abe,transparent:true,opacity:.24});
    const glass=new THREE.MeshPhysicalMaterial({color:0x0c6087,emissive:0x08334d,emissiveIntensity:.2,metalness:.12,roughness:.1,transparent:true,opacity:.46,depthWrite:false,side:THREE.DoubleSide});
    const solar=new THREE.MeshStandardMaterial({color:0x042560,emissive:0x063d98,emissiveIntensity:.12,metalness:.34,roughness:.3,side:THREE.DoubleSide});
    const dark=new THREE.MeshStandardMaterial({color:0x10151b,metalness:.74,roughness:.38});
    function box(w,h,d,mat,x,y,z,outlined=false){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat);m.position.set(x,y,z);home.add(m);if(outlined){const l=new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone());l.position.copy(m.position);home.add(l);}return m;}
    box(W,H,D,steel,W/2,H/2,D/2);
    // Existing pitched roof, garage and porch proportions retained as world coordinates.
    const frontRoof=quad([0,H,D],[W,H,D],[1.96,RIDGE,D/2],[0,RIDGE,D/2],roofMat);home.add(frontRoof);
    const hipRoof=quad([W,H,0],[W,H,D],[1.96,RIDGE,D/2],[1.96,RIDGE,D/2],roofMat);home.add(hipRoof);
    [frontRoof,hipRoof].forEach(m=>home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone())));
    box(.25,.46,.19,new THREE.MeshStandardMaterial({color:0x302e2f,metalness:.12,roughness:.9}),.445,2.35,.815,true);
    box(.77,.71,1.67,new THREE.MeshPhysicalMaterial({color:0x172b37,emissive:0x061c2a,emissiveIntensity:.18,metalness:.28,roughness:.68,transparent:true,opacity:.3,depthWrite:false}),2.885,.355,1.035);
    const gRoof=quad([W,.89,.20],[3.27,.71,.20],[3.27,.71,1.87],[W,.89,1.87],roofMat);home.add(gRoof);home.add(new THREE.LineSegments(new THREE.EdgesGeometry(gRoof.geometry),edge.clone()));
    box(.54,.72,.32,new THREE.MeshPhysicalMaterial({color:0x182b36,emissive:0x061b29,emissiveIntensity:.15,metalness:.22,roughness:.72,transparent:true,opacity:.32,depthWrite:false}),1.93,.36,1.81);
    const pRoof=quad([1.62,.84,D],[2.24,.84,D],[2.24,.75,2.01],[1.62,.75,2.01],roofMat);home.add(pRoof);
    // Thin fascia/eaves make the pitched roof read as a constructed volume.
    const fascia=new THREE.MeshStandardMaterial({color:0x111821,metalness:.52,roughness:.5});
    function trim(w,h,d,x,y,z){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),fascia);m.position.set(x,y,z);home.add(m);}
    trim(W+.08,.055,.07,W/2,H,D+.025);trim(.07,.055,D+.08,W+.025,H,D/2);trim(.07,.055,D+.08,-.025,H,D/2);trim(.08,.06,.08,1.96,RIDGE,D/2);
    // Two suspended illuminated slabs and a few translucent partitions make
    // the actual two-storey layout immediately readable through the shell.
    const floorMat=new THREE.MeshStandardMaterial({color:0x0b4964,emissive:0x0b8ab6,emissiveIntensity:.38,transparent:true,opacity:.32,depthWrite:false,side:THREE.DoubleSide});
    const partitionMat=new THREE.MeshPhysicalMaterial({color:0x0a3b52,emissive:0x0b4160,emissiveIntensity:.18,transparent:true,opacity:.22,depthWrite:false,side:THREE.DoubleSide});
    function innerFrame(w,d,y){const g=new THREE.EdgesGeometry(new THREE.BoxGeometry(w,.028,d));const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x4db6de,transparent:true,opacity:.38}));l.position.set(W/2,y,D/2);home.add(l);}
    box(2.28,.045,1.48,floorMat,1.25,.80,.825);innerFrame(2.28,1.48,.80);
    box(2.22,.032,1.42,floorMat,1.25,.12,.825);innerFrame(2.22,1.42,.12);
    box(.028,.70,1.28,partitionMat,.96,.43,.82);
    box(.72,.70,.028,partitionMat,1.68,.43,.78);
    box(.028,.70,1.2,partitionMat,1.26,1.20,.82);
    box(.65,.70,.028,partitionMat,.79,1.20,.80);
    // Windows are actual translucent emissive planes; only real light state changes them.
    const windows=[];
    function window(w,h,x,y,z,room){
      const recess=new THREE.Mesh(new THREE.PlaneGeometry(w+.12,h+.12),wallInset);recess.position.set(x,y,z-.01);home.add(recess);
      const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),glass.clone());m.position.set(x,y,z+.012);windows.push({m,room});home.add(m);
      const frameMat=new THREE.MeshStandardMaterial({color:0x596b76,metalness:.72,roughness:.28});
      for(const [fw,fh,fx,fy] of [[w+.12,.035,x,y+h/2+.035],[w+.12,.035,x,y-h/2-.035],[.035,h+.12,x-w/2-.035,y],[.035,h+.12,x+w/2+.035,y]]){const f=new THREE.Mesh(new THREE.BoxGeometry(fw,fh,.05),frameMat);f.position.set(fx,fy,z+.02);home.add(f);}
      return m;
    }
    window(.84,.44,.60,1.24,D+.012,'bedroom');window(.64,.44,1.74,1.24,D+.013,'upstairs');window(1.02,.42,.68,.49,D+.014,'livingroom');
    const door=window(.34,.54,1.93,.36,2.013,'door');door.material.color.setHex(0x1a536e);
    // Curtains remain real-state geometry and slide, rather than changing the window material.
    const curtainMat=new THREE.MeshStandardMaterial({color:0x303a48,metalness:.25,roughness:.65,transparent:true,opacity:.88});
    const curtains=[new THREE.Mesh(new THREE.BoxGeometry(.48,.43,.025),curtainMat),new THREE.Mesh(new THREE.BoxGeometry(.48,.43,.025),curtainMat.clone())];
    curtains.forEach(m=>{m.position.set(.68,.49,D+.03);home.add(m);});
    // Recessed sectional garage door, with physical slats rather than a flat outline.
    const garageDoor=new THREE.Mesh(new THREE.PlaneGeometry(.58,.52),wallInset);garageDoor.position.set(2.89,.34,1.873);home.add(garageDoor);
    for(let y=.13;y<.58;y+=.09){const slat=new THREE.Mesh(new THREE.BoxGeometry(.59,.018,.028),new THREE.MeshStandardMaterial({color:0x4b5963,metalness:.65,roughness:.34}));slat.position.set(2.89,y,1.886);home.add(slat);}
    // Individual photovoltaic panels stay flush to their original roof pitch.
    const panels=[];const roof=(x,u)=>[x,H+(RIDGE-H)*u,D-u*D/2];
    const mix=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
    for(let r=0;r<2;r++)for(let c=0;c<4;c++){
      const x0=.16+c*.29,x1=x0+.26,u0=.16+r*.26,u1=u0+.24,a=roof(x0,u0),b=roof(x1,u0),cc=roof(x1,u1),d=roof(x0,u1);
      const m=quad(a,b,cc,d,solar.clone());home.add(m);panels.push(m);home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),new THREE.LineBasicMaterial({color:0x6fbce7,transparent:true,opacity:.58})));
      const cell=new THREE.BufferGeometry(),lines=[];
      for(let i=1;i<3;i++){lines.push(...mix(a,b,i/3),...mix(d,cc,i/3));}
      for(let i=1;i<3;i++){lines.push(...mix(a,d,i/3),...mix(b,cc,i/3));}
      cell.setAttribute('position',new THREE.Float32BufferAttribute(lines,3));home.add(new THREE.LineSegments(cell,new THREE.LineBasicMaterial({color:0x3a83bb,transparent:true,opacity:.52})));
    }
    // The existing car becomes a real shaded model, still deliberately dark.
    const car=new THREE.Group();home.add(car);
    const carPaint=new THREE.MeshStandardMaterial({color:0x121c27,metalness:.56,roughness:.48});
    const carBody=new THREE.Mesh(new THREE.BoxGeometry(1.3,.16,.5),carPaint);carBody.position.set(.78,.22,2.24);car.add(carBody);
    const bonnet=new THREE.Mesh(new THREE.BoxGeometry(.43,.08,.47),carPaint);bonnet.position.set(1.2,.34,2.24);car.add(bonnet);
    const rear=new THREE.Mesh(new THREE.BoxGeometry(.22,.07,.47),carPaint);rear.position.set(.24,.32,2.24);car.add(rear);
    const cabin=taperedCabin(new THREE.MeshPhysicalMaterial({color:0x092b42,metalness:.28,roughness:.1,transparent:true,opacity:.8}));cabin.position.set(.75,.31,2.24);car.add(cabin);
    const screen=new THREE.Mesh(new THREE.PlaneGeometry(.38,.19),new THREE.MeshPhysicalMaterial({color:0x1b6b91,metalness:.15,roughness:.08,transparent:true,opacity:.55,side:THREE.DoubleSide}));screen.rotation.y=Math.PI/2;screen.position.set(1.02,.49,2.24);car.add(screen);
    for(const x of [.35,1.2])for(const z of [2.01,2.47]){const tyre=new THREE.Mesh(new THREE.CylinderGeometry(.125,.125,.07,14),dark);tyre.rotation.x=Math.PI/2;tyre.position.set(x,.13,z);car.add(tyre);const hub=new THREE.Mesh(new THREE.CylinderGeometry(.052,.052,.074,12),new THREE.MeshStandardMaterial({color:0x52616b,metalness:.85,roughness:.28}));hub.rotation.x=Math.PI/2;hub.position.set(x,.13,z);car.add(hub);}
    const carChargeLed=new THREE.Mesh(new THREE.SphereGeometry(.025,10,8),new THREE.MeshBasicMaterial({color:0xff9b4a,transparent:true,opacity:0}));carChargeLed.position.set(.16,.25,2.48);car.add(carChargeLed);
    scene.add(new THREE.HemisphereLight(0x466477,0x010203,.26));
    const key=new THREE.DirectionalLight(0x9ab9c9,.68);key.position.set(-4,6,5);scene.add(key);
    const rim=new THREE.DirectionalLight(0x28688c,.24);rim.position.set(4,3,-4);scene.add(rim);
    // Interior warmth is local to the living room.  Keeping its falloff short
    // prevents it from bleaching the parked car when a room light is on.
    const amber=new THREE.PointLight(0xffa344,.04,.82,2);amber.position.set(.7,.65,1.22);home.add(amber);
    const particles=[],flowLines=[],sprite=glowTexture();
    const paths=[[[.72,1.94,.92],[.92,1.45,1.05],[1.2,.83,1.05]],[[4,.17,2.5],[3.1,.35,2.0],[1.2,.78,1.05]],[[1.2,.78,1.05],[1.7,.60,.68],[2.4,.42,.32]]];
    const colours=[0x48d9ff,0xffaf62,0x7ae8ff];
    for(let p=0;p<3;p++){const group=new THREE.Group();home.add(group);for(let i=0;i<16;i++){const s=new THREE.Sprite(new THREE.SpriteMaterial({map:sprite,color:colours[p],transparent:true,opacity:0,depthWrite:false,blending:THREE.AdditiveBlending}));s.scale.set(.09,.09,.09);group.add(s);}particles.push(group);const g=new THREE.BufferGeometry().setFromPoints(paths[p].map(v=>new THREE.Vector3(...v)));const m=new THREE.LineDashedMaterial({color:colours[p],transparent:true,opacity:0,dashSize:.09,gapSize:.13,depthWrite:false,blending:THREE.AdditiveBlending});const l=new THREE.Line(g,m);l.computeLineDistances();home.add(l);flowLines.push(m);}
    // Sparse fixed points create a restrained holographic interior, not a
    // noisy backdrop.  They shimmer gently with the scan state.
    const pointPositions=[];for(let i=0;i<42;i++){const x=.14+((i*37)%100)/100*2.22,y=.18+((i*53)%100)/100*1.32,z=.14+((i*71)%100)/100*1.34;pointPositions.push(x,y,z);}
    const pointGeometry=new THREE.BufferGeometry();pointGeometry.setAttribute('position',new THREE.Float32BufferAttribute(pointPositions,3));
    const holoPoints=new THREE.Points(pointGeometry,new THREE.PointsMaterial({color:0x4dceff,size:.018,transparent:true,opacity:.18,depthWrite:false,sizeAttenuation:true}));home.add(holoPoints);
    // A travelling, thin rectangular scan contour gives the requested scan
    // without the broad translucent band that looked like a rendering error.
    const scan=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(2.62,.018,1.78)),new THREE.LineBasicMaterial({color:0x63d7ff,transparent:true,opacity:0,depthWrite:false}));scan.position.set(1.31,.1,.89);home.add(scan);
    function pathAt(path,t){const n=path.length-1,i=Math.min(n-1,Math.floor(t*n)),f=t*n-i,a=path[i],b=path[i+1];return[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,a[2]+(b[2]-a[2])*f];}
    return {frame(now){
      if(now-received>30)state={};
      const rooms=state.rooms||{},solarWatts=Math.max(0,Number(state.solar_watts)||0),watts=Math.max(0,Number(state.watts_now)||0);
      const solarPower=clamp(solarWatts/2800,0,1), importPower=clamp(Math.max(0,watts-solarWatts)/1600,0,1), batteryPower=state.battery&&state.battery.charging===true?1:0;
      const levels=[solarPower,importPower,batteryPower];eventEnergy*=.978;
      panels.forEach((m,i)=>{m.material.emissiveIntensity=.1+solarPower*.42+Math.sin(now*1.5+i)*solarPower*.035;m.material.color.setHSL(.61,.84,.16+solarPower*.07);});
      windows.forEach(w=>{const lit=rooms[w.room]&&rooms[w.room].light===true;w.m.material.color.setHex(lit?0x7a3f14:0x0c496a);w.m.material.emissive.setHex(lit?0xc05a12:0x08263b);w.m.material.emissiveIntensity=lit?.32+.06*Math.sin(now*1.2):.12;});
      amber.intensity=(rooms.livingroom&&rooms.livingroom.light?.28:.02)+eventEnergy*.06;
      const living=rooms.livingroom||{};const open=num(living.curtain_position)?clamp(living.curtain_position/100,0,1):(living.curtain==='closed'?0:1);curtains[0].position.x=.68-(.24*open);curtains[1].position.x=.68+(.24*open);curtains[0].scale.x=curtains[1].scale.x=.95-open*.78;
      carChargeLed.material.opacity=state.car&&state.car.charging===true?.42+.14*Math.sin(now*3):0;
      for(let g=0;g<3;g++){const level=levels[g],group=particles[g];group.visible=level>.015;flowLines[g].opacity=.025+level*.32;flowLines[g].dashOffset=-now*(.3+level*.75);group.children.forEach((s,i)=>{const t=(now*(.11+level*.23)+i/group.children.length+g*.23)%1;s.position.fromArray(pathAt(paths[g],t));s.material.opacity=(.08+level*.28)*(i%3?1:.62);s.scale.setScalar((.045+level*.052)*(i%3?1:.72));});}
      const phase=now%24,scanning=phase>18&&phase<20.8;
      scan.material.opacity=scanning?.3*Math.sin((phase-18)/2.8*Math.PI):0;
      scan.position.y=.12+(scanning?(phase-18)/2.8*1.72:0);
      holoPoints.material.opacity=.12+(scanning?.12:0)+Math.sin(now*.7)*.025;
      home.rotation.y=-.16+Math.sin(now*.10)*.025;home.position.y=Math.sin(now*.16)*.018;camera.position.x=-5.1+Math.sin(now*.10)*.11;camera.position.z=5.4+Math.cos(now*.10)*.09;camera.lookAt(1.55,.9,.95);renderer.render(scene,camera);
    },dispose(){renderer.dispose();canvas.remove();}};
  }
  function render(){return '';} // no SVG fallback: the house is a WebGL scene.
  function mount(el){let fx;return now=>{if(!fx)fx=buildScene(el);if(fx)fx.frame(now);};}
  return {update,render,mount};
})();
