/* Live house renderer. Geometry is the existing house, now drawn natively in
   Three.js; HA data arrives through the existing bridge and is never fetched here. */
const HomeTwin = (() => {
  'use strict';
  const W=2.5,D=1.65,H=1.65,RIDGE=2.23;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  let state={}, received=-Infinity;

  function update(data, now=performance.now()/1000) {
    state=data||{}; received=now;
  }
  function quad(a,b,c,d,material) {
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.Float32BufferAttribute([...a,...b,...c,...d],3));
    g.setIndex([0,1,2,0,2,3]);g.computeVertexNormals();
    return new THREE.Mesh(g,material);
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
    const camera=new THREE.PerspectiveCamera(35,660/410,.1,30);camera.position.set(-5.1,3.75,5.4);camera.lookAt(1.55,1.08,.95);
    const home=new THREE.Group();scene.add(home);
    // Both habitable storeys gain the requested 20% vertical volume.  The
    // car cancels this scale locally below, so it stays a normal-sized vehicle.
    home.scale.y=1.2;
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
    // The matching rear pitch was absent, leaving the roof open when seen
    // through the translucent shell.  Keep the roof coordinates fixed; this
    // simply closes the existing pitched volume behind the ridge.
    const backRoof=quad([0,H,0],[W,H,0],[1.96,RIDGE,D/2],[0,RIDGE,D/2],roofMat);home.add(backRoof);
    const hipRoof=quad([W,H,0],[W,H,D],[1.96,RIDGE,D/2],[1.96,RIDGE,D/2],roofMat);home.add(hipRoof);
    [frontRoof,backRoof,hipRoof].forEach(m=>home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone())));
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
    const floorMat=new THREE.MeshStandardMaterial({color:0x0a4058,emissive:0x0b789c,emissiveIntensity:.28,transparent:true,opacity:.22,depthWrite:false,side:THREE.DoubleSide});
    const upperFloorMat=floorMat.clone();upperFloorMat.color.setHex(0x0b4a63);upperFloorMat.emissive.setHex(0x0b88ae);upperFloorMat.opacity=.28;
    function innerFrame(w,d,y){const g=new THREE.EdgesGeometry(new THREE.BoxGeometry(w,.028,d));const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x4db6de,transparent:true,opacity:.38}));l.position.set(W/2,y,D/2);home.add(l);}
    // The upper slab remains visible through the shell, but without a bright
    // perimeter that reads as an accidental band through the first-floor windows.
    box(2.28,.025,1.48,upperFloorMat,1.25,.80,.825);
    box(2.22,.032,1.42,floorMat,1.25,.12,.825);innerFrame(2.22,1.42,.12);
    // Named, individual thermal zones sit almost invisibly within each floor.
    // They are deliberately separate meshes so future HA state can colour a
    // room without needing to rebuild the architecture.
    const roomAnchors={
      hallway:[.40,.43,.83], livingroom:[1.62,.43,1.24], kitchen:[1.62,.43,.40],
      bedroom1:[.63,1.20,1.24], bedroom2:[1.82,1.20,1.24],
      bedroom3:[.63,1.20,.40], bathroom:[1.82,1.20,.40]
    };
    home.userData.roomAnchors=roomAnchors;
    const roomZones={};
    function roomZone(name,w,d,x,y,z){const mat=new THREE.MeshStandardMaterial({color:0x0b5270,emissive:0x063047,emissiveIntensity:.18,transparent:true,opacity:.035,depthWrite:false,side:THREE.DoubleSide});const m=new THREE.Mesh(new THREE.PlaneGeometry(w,d),mat);m.rotation.x=-Math.PI/2;m.position.set(x,y,z);m.name='zone-'+name;m.userData={room:name,thermal:true};home.add(m);roomZones[name]=m;}
    roomZone('hallway',.72,1.38,.43,.145,.825);roomZone('livingroom',1.48,.66,1.62,.145,1.18);roomZone('kitchen',1.48,.66,1.62,.145,.47);
    roomZone('bedroom1',1.02,.66,.64,.825,1.18);roomZone('bedroom2',1.02,.66,1.86,.825,1.18);roomZone('bedroom3',1.02,.66,.64,.825,.47);roomZone('bathroom',1.02,.66,1.86,.825,.47);
    home.userData.roomZones=roomZones;
    // Floor-plan boundaries replace full-height transparent blue walls. They
    // remain readable from any orbit, but cannot alpha-stack into opaque blocks.
    function planBoundaries(y,segments){const v=[];segments.forEach(s=>v.push(s[0],y,s[1],s[2],y,s[3]));const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(v,3));home.add(new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x52b7dc,transparent:true,opacity:.42,depthWrite:false})));}
    function cornerPost(x,z,y0,y1){const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,y0,z),new THREE.Vector3(x,y1,z)]);home.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0x3b91b4,transparent:true,opacity:.2,depthWrite:false})));}
    planBoundaries(.155,[[.82,.13,.82,1.52],[.82,.825,2.38,.825]]);
    planBoundaries(.835,[[1.25,.13,1.25,1.52],[.14,.825,2.36,.825]]);
    cornerPost(.82,.825,.15,.76);cornerPost(1.25,.825,.83,1.54);
    // Windows are actual translucent emissive planes; only real light state changes them.
    const windows=[];
    function window(w,h,x,y,z,room){
      const recess=new THREE.Mesh(new THREE.PlaneGeometry(w+.12,h+.12),wallInset);recess.position.set(x,y,z-.01);home.add(recess);
      const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),glass.clone());m.position.set(x,y,z+.012);windows.push({m,room});home.add(m);
      const frameMat=new THREE.MeshStandardMaterial({color:0x596b76,metalness:.72,roughness:.28}),frame=.021,lip=.024;
      for(const [fw,fh,fx,fy] of [[w+.08,frame,x,y+h/2+lip],[w+.08,frame,x,y-h/2-lip],[frame,h+.08,x-w/2-lip,y],[frame,h+.08,x+w/2+lip,y]]){const f=new THREE.Mesh(new THREE.BoxGeometry(fw,fh,.05),frameMat);f.position.set(fx,fy,z+.02);home.add(f);}
      return m;
    }
    window(.84,.352,.60,1.284,D+.012,'bedroom');window(.64,.352,1.74,1.284,D+.013,'upstairs');window(1.02,.42,.68,.49,D+.014,'livingroom');
    const door=window(.34,.54,1.93,.36,2.013,'door');door.material.color.setHex(0x1a536e);
    // Tiny physical camera details belong to the architecture, not to a UI
    // overlay.  They use existing porch/external camera/motion state below.
    const doorbell=new THREE.Group();home.add(doorbell);
    const doorbellBody=new THREE.Mesh(new THREE.BoxGeometry(.065,.17,.034),new THREE.MeshStandardMaterial({color:0x18252d,metalness:.72,roughness:.3}));doorbellBody.position.set(1.68,.43,2.035);doorbell.add(doorbellBody);
    const doorbellLens=new THREE.Mesh(new THREE.SphereGeometry(.019,10,8),new THREE.MeshBasicMaterial({color:0x285b72,transparent:true,opacity:.5}));doorbellLens.position.set(1.68,.47,2.06);doorbell.add(doorbellLens);
    const frontCamera=new THREE.Group();home.add(frontCamera);
    const cameraMount=new THREE.Mesh(new THREE.CylinderGeometry(.026,.026,.13,10),new THREE.MeshStandardMaterial({color:0x202b32,metalness:.68,roughness:.34}));cameraMount.rotation.x=Math.PI/2;cameraMount.position.set(1.86,.96,1.98);frontCamera.add(cameraMount);
    const cameraBody=new THREE.Mesh(new THREE.BoxGeometry(.13,.075,.085),new THREE.MeshStandardMaterial({color:0x17232c,metalness:.64,roughness:.3}));cameraBody.position.set(1.86,.98,2.04);frontCamera.add(cameraBody);
    const cameraLens=new THREE.Mesh(new THREE.SphereGeometry(.026,10,8),new THREE.MeshBasicMaterial({color:0x285b72,transparent:true,opacity:.5}));cameraLens.position.set(1.86,.98,2.093);frontCamera.add(cameraLens);
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
    const car=new THREE.Group();car.position.z=.34;car.scale.y=1/1.2;home.add(car);
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
    // Sparse fixed points give the transparent twin internal depth without
    // turning into an animated electrical effect.
    const pointPositions=[];for(let i=0;i<42;i++){const x=.14+((i*37)%100)/100*2.22,y=.18+((i*53)%100)/100*1.32,z=.14+((i*71)%100)/100*1.34;pointPositions.push(x,y,z);}
    const pointGeometry=new THREE.BufferGeometry();pointGeometry.setAttribute('position',new THREE.Float32BufferAttribute(pointPositions,3));
    const holoPoints=new THREE.Points(pointGeometry,new THREE.PointsMaterial({color:0x4dceff,size:.018,transparent:true,opacity:.18,depthWrite:false,sizeAttenuation:true}));home.add(holoPoints);
    return {frame(now){
      if(now-received>30)state={};
      const rooms=state.rooms||{},solarWatts=Math.max(0,Number(state.solar_watts)||0);
      const solarPower=clamp(solarWatts/2800,0,1);
      panels.forEach(m=>{m.material.emissiveIntensity=.1+solarPower*.42;m.material.color.setHSL(.61,.84,.16+solarPower*.07);});
      windows.forEach(w=>{const lit=rooms[w.room]&&rooms[w.room].light===true;w.m.material.color.setHex(lit?0x7a3f14:0x0c496a);w.m.material.emissive.setHex(lit?0xc05a12:0x08263b);w.m.material.emissiveIntensity=lit?.32+.06*Math.sin(now*1.2):.12;});
      amber.intensity=rooms.livingroom&&rooms.livingroom.light?.28:.02;
      const living=rooms.livingroom||{};const open=num(living.curtain_position)?clamp(living.curtain_position/100,0,1):(living.curtain==='closed'?0:1);curtains[0].position.x=.68-(.24*open);curtains[1].position.x=.68+(.24*open);curtains[0].scale.x=curtains[1].scale.x=.95-open*.78;
      carChargeLed.material.opacity=state.car&&state.car.charging===true?.42:0;
      const cameras=state.cameras||{},porchActive=rooms.porch&&rooms.porch.occupied===true,externalActive=rooms.external&&rooms.external.occupied===true;
      doorbellLens.material.color.setHex(porchActive?0xffa34a:0x285b72);doorbellLens.material.opacity=porchActive?.7+.15*Math.sin(now*5):(cameras.doorbell ? .5 : .28);
      cameraLens.material.color.setHex(externalActive?0xffa34a:0x285b72);cameraLens.material.opacity=externalActive?.7+.15*Math.sin(now*5.3):(cameras.external ? .5 : .28);
      holoPoints.material.opacity=.14;
      // A slow front-only orbit reveals depth without making the home feel as
      // though it is rotating.  One 96-second left-to-right-and-back sweep.
      const orbit=Math.sin(now*.065);home.rotation.y=-.16;home.position.y=0;camera.position.x=-5.1+orbit*1.05;camera.position.z=5.55+Math.cos(now*.065)*.16;camera.lookAt(1.55,1.08,.95);renderer.render(scene,camera);
    },dispose(){renderer.dispose();canvas.remove();}};
  }
  function render(){return '';} // no SVG fallback: the house is a WebGL scene.
  function mount(el){let fx;return now=>{if(!fx)fx=buildScene(el);if(fx)fx.frame(now);};}
  return {update,render,mount};
})();
