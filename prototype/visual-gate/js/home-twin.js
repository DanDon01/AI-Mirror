/* Live house renderer. Geometry is the existing house, now drawn natively in
   Three.js; HA data arrives through the existing bridge and is never fetched here. */
const HomeTwin = (() => {
  'use strict';
  const W=2.5,X0=-.5,MAIN_W=W-X0,MAIN_C=(W+X0)/2,GARAGE_W=.77*1.15,GARAGE_C=W+(.77*1.15)/2,GARAGE_X=W+.77*1.15,D=1.65,H=1.65,RIDGE=2.23;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  let state={}, received=-Infinity;
  // This survives a panel rebuild when a fresh live snapshot arrives.  A
  // static HA curtain state must not replay its movement every polling pass.
  const curtainState={known:false,target:1,open:1,lastAt:null,eventUntil:0};

  function curtainTarget(data) {
    const living=data&&data.rooms&&data.rooms.livingroom;
    if(!living)return null;
    if(num(living.curtain_position))return clamp(living.curtain_position/100,0,1);
    if(living.curtain==='closed')return 0;
    if(living.curtain==='open')return 1;
    return null;
  }

  function update(data, now=performance.now()/1000) {
    state=data||{}; received=now;
    const nextCurtain=curtainTarget(state);
    if(nextCurtain!==null){
      if(!curtainState.known){curtainState.known=true;curtainState.target=curtainState.open=nextCurtain;}
      else if(Math.abs(nextCurtain-curtainState.target)>.005){curtainState.target=nextCurtain;curtainState.lastAt=null;curtainState.eventUntil=now+4.5;}
    }
  }
  function setTuning(tuning) {
    // Tuning changes deliberately avoid rebuilding the Three renderer. The
    // control page can therefore steer an already visible house immediately.
    state=Object.assign({},state,{_tuning:tuning||{}});
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
    // A larger lower-right stage gives the live twin enough presence to read
    // as the house rather than a small status icon. Its centre remains fixed,
    // so it grows into the surrounding black glass rather than shifting the
    // rest of the mirror layout.
    const canvas=document.createElement('canvas');canvas.className='home-twin-webgl';canvas.width=1100;canvas.height=680;el.textContent='';el.appendChild(canvas);
    const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'high-performance'});
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.35));renderer.setSize(1100,680,false);renderer.setClearColor(0x000000,0);
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;renderer.outputEncoding=THREE.sRGBEncoding;
    const scene=new THREE.Scene();
    // View from the real home's left-front side: garage and porch lead.
    const camera=new THREE.PerspectiveCamera(33,1100/680,.1,30);camera.position.set(-5.1,4.25,6.5);camera.lookAt(1.25,1.08,.95);
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
    // The screen-right blank wall (opposite the garage) is extruded by 20%.
    // X0 is the physical screen-right side because the presentation is mirrored.
    box(MAIN_W,H,D,steel,MAIN_C,H/2,D/2);
    const frontRoof=quad([X0,H,D],[W,H,D],[1.96,RIDGE,D/2],[X0,RIDGE,D/2],roofMat);home.add(frontRoof);
    // The matching rear pitch was absent, leaving the roof open when seen
    // through the translucent shell.  Keep the roof coordinates fixed; this
    // simply closes the existing pitched volume behind the ridge.
    const backRoof=quad([X0,H,0],[W,H,0],[1.96,RIDGE,D/2],[X0,RIDGE,D/2],roofMat);home.add(backRoof);
    const hipRoof=quad([W,H,0],[W,H,D],[1.96,RIDGE,D/2],[1.96,RIDGE,D/2],roofMat);home.add(hipRoof);
    [frontRoof,backRoof,hipRoof].forEach(m=>home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone())));
    box(.25,.46,.19,new THREE.MeshStandardMaterial({color:0x302e2f,metalness:.12,roughness:.9}),.445,2.35,.815,true);
    box(GARAGE_W,.71,1.67,new THREE.MeshPhysicalMaterial({color:0x172b37,emissive:0x061c2a,emissiveIntensity:.18,metalness:.28,roughness:.68,transparent:true,opacity:.3,depthWrite:false}),GARAGE_C,.355,1.035);
    const gRoof=quad([W,.89,.20],[GARAGE_X,.71,.20],[GARAGE_X,.71,1.87],[W,.89,1.87],roofMat);home.add(gRoof);home.add(new THREE.LineSegments(new THREE.EdgesGeometry(gRoof.geometry),edge.clone()));
    box(.702,.72,.32,new THREE.MeshPhysicalMaterial({color:0x182b36,emissive:0x061b29,emissiveIntensity:.15,metalness:.22,roughness:.72,transparent:true,opacity:.32,depthWrite:false}),1.93,.36,1.81);
    const pRoof=quad([1.539,.84,D],[2.321,.84,D],[2.321,.75,2.01],[1.539,.75,2.01],roofMat);home.add(pRoof);
    // Thin fascia/eaves make the pitched roof read as a constructed volume.
    const fascia=new THREE.MeshStandardMaterial({color:0x111821,metalness:.52,roughness:.5});
    function trim(w,h,d,x,y,z){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),fascia);m.position.set(x,y,z);home.add(m);}
    trim(MAIN_W+.08,.055,.07,MAIN_C,H,D+.025);trim(.07,.055,D+.08,W+.025,H,D/2);trim(.07,.055,D+.08,X0-.025,H,D/2);trim(.08,.06,.08,1.96,RIDGE,D/2);
    // Two suspended illuminated slabs and a few translucent partitions make
    // the actual two-storey layout immediately readable through the shell.
    // Each storey owns a separate thermal plane. They remain translucent
    // enough to read as part of a holographic house, but are bright enough
    // that a real downstairs/upstairs temperature is visible at a glance.
    // Basic material deliberately bypasses scene lighting and tone mapping:
    // these are measured thermal colours, so 22°C must remain orange rather
    // than being washed into the neutral architectural lighting.
    const floorMat=new THREE.MeshBasicMaterial({color:0x0a4058,transparent:true,opacity:.14,depthWrite:false,side:THREE.DoubleSide});
    const upperFloorMat=floorMat.clone();upperFloorMat.color.setHex(0x0b4a63);
    function innerFrame(w,d,y){const g=new THREE.EdgesGeometry(new THREE.BoxGeometry(w,.028,d));const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x4db6de,transparent:true,opacity:.38}));l.position.set(MAIN_C,y,D/2);home.add(l);}
    // The upper slab remains visible through the shell, but without a bright
    // perimeter that reads as an accidental band through the first-floor windows.
    const upperFloor=box(2.78,.025,1.48,upperFloorMat,1.00,.87,.825);
    const groundFloor=box(2.92,.024,1.58,floorMat,1.00,.10,.825);innerFrame(2.92,1.58,.10);
    // Named, individual thermal zones sit almost invisibly within each floor.
    // They are deliberately separate meshes so future HA state can colour a
    // room without needing to rebuild the architecture.
    const roomAnchors={
      hallway:[2.02,.43,.83], livingroom:[.90,.43,1.24], kitchen:[.90,.43,.40],
      bedroom1:[.44,1.20,1.24], bedroom2:[1.82,1.20,1.24],
      bedroom3:[.44,1.20,.40], bathroom:[1.82,1.20,.40]
    };
    home.userData.roomAnchors=roomAnchors;
    const roomZones={};
    function roomZone(name,w,d,x,y,z){const mat=new THREE.MeshStandardMaterial({color:0x0b5270,emissive:0x063047,emissiveIntensity:.18,transparent:true,opacity:.035,depthWrite:false,side:THREE.DoubleSide});const m=new THREE.Mesh(new THREE.PlaneGeometry(w,d),mat);m.rotation.x=-Math.PI/2;m.position.set(x,y,z);m.name='zone-'+name;m.userData={room:name,thermal:true};home.add(m);roomZones[name]=m;}
    // The front elevation is mirrored for the real home's left-front view:
    // the narrow entrance hall lies behind the porch at screen-left.
    roomZone('hallway',.68,1.52,2.02,.055,.825);roomZone('livingroom',1.48,.72,.90,.055,1.19);roomZone('kitchen',1.48,.72,.90,.055,.46);
    roomZone('bedroom1',1.58,.66,.44,.825,1.18);roomZone('bedroom2',1.02,.66,1.86,.825,1.18);roomZone('bedroom3',1.58,.66,.44,.825,.47);roomZone('bathroom',1.02,.66,1.86,.825,.47);
    home.userData.roomZones=roomZones;
    // Floor-plan boundaries replace full-height transparent blue walls. They
    // remain readable from any orbit, but cannot alpha-stack into opaque blocks.
    function planBoundaries(y,segments){const v=[];segments.forEach(s=>v.push(s[0],y,s[1],s[2],y,s[3]));const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(v,3));home.add(new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x52b7dc,transparent:true,opacity:.42,depthWrite:false})));}
    function cornerPost(x,z,y0,y1){const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,y0,z),new THREE.Vector3(x,y1,z)]);home.add(new THREE.Line(g,new THREE.LineBasicMaterial({color:0x3b91b4,transparent:true,opacity:.2,depthWrite:false})));}
    planBoundaries(.06,[[1.68,.04,1.68,1.61],[-.46,.825,1.68,.825]]);
    planBoundaries(.835,[[1.25,.13,1.25,1.52],[-.36,.825,2.36,.825]]);
    cornerPost(1.68,.825,.05,.76);cornerPost(1.25,.825,.83,1.54);
    // Windows are actual translucent emissive planes; only real light state changes them.
    const windows=[];
    function window(w,h,x,y,z,room){
      const recess=new THREE.Mesh(new THREE.PlaneGeometry(w+.12,h+.12),wallInset);recess.position.set(x,y,z-.01);home.add(recess);
      const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),glass.clone());m.position.set(x,y,z+.012);windows.push({m,room});home.add(m);
      const frameMat=new THREE.MeshStandardMaterial({color:0x596b76,metalness:.72,roughness:.28}),frame=.021,lip=.024;
      for(const [fw,fh,fx,fy] of [[w+.08,frame,x,y+h/2+lip],[w+.08,frame,x,y-h/2-lip],[frame,h+.08,x-w/2-lip,y],[frame,h+.08,x+w/2+lip,y]]){const f=new THREE.Mesh(new THREE.BoxGeometry(fw,fh,.05),frameMat);f.position.set(fx,fy,z+.02);home.add(f);}
      return m;
    }
    window(.84,.352,.10,1.284,D+.012,'bedroom');window(.64,.352,1.74,1.284,D+.013,'upstairs');window(1.02,.42,.18,.49,D+.014,'livingroom');
    const door=window(.34,.54,1.93,.36,2.013,'door');door.material.color.setHex(0x1a536e);door.material.opacity=.84;
    // The contact sensor drives a physical entrance door, not a text status.
    // The surrounding frame stays in the facade while the leaf pivots inward
    // about its left hinge, exposing the hall when the real contact is open.
    home.remove(door);
    const doorPivot=new THREE.Group();doorPivot.position.set(1.76,.36,2.025);door.position.set(.17,0,0);doorPivot.add(door);home.add(doorPivot);
    window(.13,.27,1.66,.50,2.014,'porch');window(.13,.27,2.20,.50,2.014,'porch');
    // Tiny physical camera details belong to the architecture, not to a UI
    // overlay.  They use existing porch/external camera/motion state below.
    const doorbell=new THREE.Group();home.add(doorbell);
    const doorbellBody=new THREE.Mesh(new THREE.BoxGeometry(.065,.17,.034),new THREE.MeshStandardMaterial({color:0x18252d,metalness:.72,roughness:.3}));doorbellBody.position.set(1.79,.43,2.035);doorbell.add(doorbellBody);
    const doorbellLens=new THREE.Mesh(new THREE.SphereGeometry(.019,10,8),new THREE.MeshBasicMaterial({color:0x285b72,transparent:true,opacity:.5}));doorbellLens.position.set(1.79,.47,2.06);doorbell.add(doorbellLens);
    const frontCamera=new THREE.Group();home.add(frontCamera);
    const cameraMount=new THREE.Mesh(new THREE.CylinderGeometry(.026,.026,.13,10),new THREE.MeshStandardMaterial({color:0x202b32,metalness:.68,roughness:.34}));cameraMount.rotation.x=Math.PI/2;cameraMount.position.set(1.86,.96,1.98);frontCamera.add(cameraMount);
    const cameraBody=new THREE.Mesh(new THREE.BoxGeometry(.13,.075,.085),new THREE.MeshStandardMaterial({color:0x17232c,metalness:.64,roughness:.3}));cameraBody.position.set(1.86,.98,2.04);frontCamera.add(cameraBody);
    const cameraLens=new THREE.Mesh(new THREE.SphereGeometry(.026,10,8),new THREE.MeshBasicMaterial({color:0x285b72,transparent:true,opacity:.5}));cameraLens.position.set(1.86,.98,2.093);frontCamera.add(cameraLens);
    // Curtains remain real-state geometry and slide, rather than changing the window material.
    const curtainMat=new THREE.MeshStandardMaterial({color:0x303a48,metalness:.25,roughness:.65,transparent:true,opacity:.88});
    const curtains=[new THREE.Mesh(new THREE.BoxGeometry(.51,.43,.025),curtainMat),new THREE.Mesh(new THREE.BoxGeometry(.51,.43,.025),curtainMat.clone())];
    curtains.forEach(m=>{m.position.set(.18,.49,D+.03);home.add(m);});
    // Recessed sectional garage door, with physical slats rather than a flat outline.
    const garageDoor=new THREE.Mesh(new THREE.PlaneGeometry(.667,.52),wallInset);garageDoor.position.set(GARAGE_C,.34,1.873);home.add(garageDoor);
    for(let y=.13;y<.58;y+=.09){const slat=new THREE.Mesh(new THREE.BoxGeometry(.677,.018,.028),new THREE.MeshStandardMaterial({color:0x4b5963,metalness:.65,roughness:.34}));slat.position.set(GARAGE_C,y,1.886);home.add(slat);}
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
    // Painted cabin and separate windscreens: a proper hard-roof EV, rather
    // than a single translucent glass canopy.
    const cabin=taperedCabin(carPaint);cabin.position.set(.75,.31,2.24);car.add(cabin);
    const hardRoof=new THREE.Mesh(new THREE.BoxGeometry(.42,.045,.36),carPaint);hardRoof.position.set(.75,.57,2.24);car.add(hardRoof);
    const autoGlass=new THREE.MeshPhysicalMaterial({color:0x0a3852,metalness:.22,roughness:.12,transparent:true,opacity:.78,side:THREE.DoubleSide});
    const windscreen=new THREE.Mesh(new THREE.PlaneGeometry(.36,.19),autoGlass);windscreen.rotation.y=Math.PI/2;windscreen.rotation.z=-.16;windscreen.position.set(1.105,.45,2.24);car.add(windscreen);
    const rearScreen=new THREE.Mesh(new THREE.PlaneGeometry(.36,.17),autoGlass.clone());rearScreen.rotation.y=Math.PI/2;rearScreen.rotation.z=.18;rearScreen.position.set(.395,.45,2.24);car.add(rearScreen);
    for(const x of [.35,1.2])for(const z of [2.01,2.47]){const tyre=new THREE.Mesh(new THREE.CylinderGeometry(.125,.125,.07,14),dark);tyre.rotation.x=Math.PI/2;tyre.position.set(x,.13,z);car.add(tyre);const hub=new THREE.Mesh(new THREE.CylinderGeometry(.052,.052,.074,12),new THREE.MeshStandardMaterial({color:0x52616b,metalness:.85,roughness:.28}));hub.rotation.x=Math.PI/2;hub.position.set(x,.13,z);car.add(hub);}
    const carChargeLed=new THREE.Mesh(new THREE.SphereGeometry(.025,10,8),new THREE.MeshBasicMaterial({color:0xff9b4a,transparent:true,opacity:0}));carChargeLed.position.set(.16,.25,2.48);car.add(carChargeLed);
    // Wall-mounted charger on the screen-right exterior side of the porch.
    const charger=new THREE.Group();home.add(charger);
    const chargerBody=new THREE.Mesh(new THREE.BoxGeometry(.05,.22,.13),new THREE.MeshStandardMaterial({color:0x16252d,metalness:.62,roughness:.34}));chargerBody.position.set(1.505,.40,1.83);charger.add(chargerBody);
    const chargerFace=new THREE.Mesh(new THREE.PlaneGeometry(.095,.16),new THREE.MeshStandardMaterial({color:0x173c4c,emissive:0x082d3d,emissiveIntensity:.18,metalness:.3,roughness:.32}));chargerFace.rotation.y=-Math.PI/2;chargerFace.position.set(1.477,.40,1.83);charger.add(chargerFace);
    const chargerLed=new THREE.Mesh(new THREE.SphereGeometry(.014,8,6),new THREE.MeshBasicMaterial({color:0x48bddd,transparent:true,opacity:.3}));chargerLed.position.set(1.47,.43,1.83);charger.add(chargerLed);
    // Real-light fixtures: deliberately few, spatial and architectural. Each
    // has a tiny physical source and a gently interpolated local light pool.
    const fixtures={};
    function fixture(name,x,y,z,colour=0xffa34a,distance=.8){
      const mat=new THREE.MeshStandardMaterial({color:0x253039,emissive:colour,emissiveIntensity:.02,metalness:.35,roughness:.35});
      const source=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,.012,12),mat);source.rotation.x=Math.PI/2;source.position.set(x,y,z);home.add(source);
      const pool=new THREE.PointLight(colour,0,distance,2);pool.position.set(x,y-.035,z);home.add(pool);
      fixtures[name]={mat,pool,level:0,colour};
    }
    fixture('porch',1.93,.69,1.94,0xffa34a,1.15);
    fixture('hallway',2.02,.66,.82,0xffbd67,.68);
    fixture('bedroom1',.44,1.48,1.18,0xffbd67,.72);fixture('bedroom2',1.82,1.48,1.18,0xffbd67,.72);
    fixture('bedroom3',.44,1.48,.47,0xffbd67,.72);fixture('bathroom',1.82,1.48,.47,0xffd594,.62);
    fixture('livingroom',.72,.67,1.18,0xffaf5b,1.15);
    fixture('spot1',.18,.67,1.18,0xffc16c,.62);fixture('spot2',.62,.67,1.18,0xffc16c,.62);fixture('spot3',1.06,.67,1.18,0xffc16c,.62);
    const ledStrip=new THREE.Mesh(new THREE.BoxGeometry(.025,.035,.88),new THREE.MeshStandardMaterial({color:0x142f3c,emissive:0x176987,emissiveIntensity:.04,metalness:.35,roughness:.3}));ledStrip.position.set(X0+.018,.55,.83);home.add(ledStrip);
    const tvScreen=new THREE.Mesh(new THREE.BoxGeometry(.035,.25,.42),new THREE.MeshStandardMaterial({color:0x070a0d,emissive:0x0a2940,emissiveIntensity:.03,metalness:.25,roughness:.32}));tvScreen.position.set(.70,.45,.22);home.add(tvScreen);
    const tvGlow=new THREE.PointLight(0x398ec2,0,.9,2);tvGlow.position.set(.66,.45,.30);home.add(tvGlow);
    // Alarm box occupies the front wall gap between the two upstairs windows.
    const alarmBox=new THREE.Mesh(new THREE.BoxGeometry(.13,.10,.038),new THREE.MeshStandardMaterial({color:0x17242d,emissive:0x18313e,emissiveIntensity:.08,metalness:.58,roughness:.3}));alarmBox.position.set(.92,1.35,D+.035);home.add(alarmBox);
    const alarmLed=new THREE.Mesh(new THREE.SphereGeometry(.018,8,6),new THREE.MeshBasicMaterial({color:0x3f8fb1,transparent:true,opacity:.35}));alarmLed.position.set(.92,1.35,D+.06);home.add(alarmLed);
    // Approximate presence only: sparse, anonymous point silhouettes map a
    // binary sensor to an area, never to a claimed exact person position.
    const figures={};
    function presenceFigure(name,x,y,z){
      const points=[0,.48,0,-.11,.33,0,.11,.33,0,-.08,.08,0,.08,.08,0,-.14,.22,0,.14,.22,0];
      const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(points,3));
      const m=new THREE.PointsMaterial({color:0x83dcff,size:.042,transparent:true,opacity:0,depthWrite:false,sizeAttenuation:true});
      const p=new THREE.Points(g,m);p.position.set(x,y,z);home.add(p);figures[name]={mesh:p,mat:m,level:0};
    }
    presenceFigure('porch',1.93,.05,2.10);presenceFigure('external',1.42,.05,2.06);
    presenceFigure('livingroom',.72,.16,1.10);presenceFigure('bedroom',.44,.84,1.18);presenceFigure('upstairs',1.82,.84,.48);
    const hemi=new THREE.HemisphereLight(0x466477,0x010203,.34);scene.add(hemi);
    const key=new THREE.DirectionalLight(0x9ab9c9,.84);key.position.set(-4,6,5);scene.add(key);
    const rim=new THREE.DirectionalLight(0x28688c,.34);rim.position.set(4,3,-4);scene.add(rim);
    // Interior warmth is local to the living room.  Keeping its falloff short
    // prevents it from bleaching the parked car when a room light is on.
    const amber=new THREE.PointLight(0xffa344,.04,.82,2);amber.position.set(.7,.65,1.22);home.add(amber);
    // Sparse fixed points give the transparent twin internal depth without
    // turning into an animated electrical effect.
    const pointPositions=[];for(let i=0;i<42;i++){const x=.14+((i*37)%100)/100*2.22,y=.18+((i*53)%100)/100*1.32,z=.14+((i*71)%100)/100*1.34;pointPositions.push(x,y,z);}
    const pointGeometry=new THREE.BufferGeometry();pointGeometry.setAttribute('position',new THREE.Float32BufferAttribute(pointPositions,3));
    const holoPoints=new THREE.Points(pointGeometry,new THREE.PointsMaterial({color:0x4dceff,size:.018,transparent:true,opacity:.18,depthWrite:false,sizeAttenuation:true}));home.add(holoPoints);
    // Environmental particles exist only for measured noteworthy weather.
    // They are outside the shell and share compact point buffers for Pi-safe use.
    function weatherField(count,colour,size){const base=[],live=[];for(let i=0;i<count;i++){const x=-.8+((i*37)%100)/100*4.2,y=.1+((i*53)%100)/100*3.1,z=-.55+((i*71)%100)/100*3.0;base.push(x,y,z);live.push(x,y,z);}const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(live,3));const m=new THREE.PointsMaterial({color:colour,size,transparent:true,opacity:0,depthWrite:false,sizeAttenuation:true});const p=new THREE.Points(g,m);scene.add(p);return{base,mesh:p,attr:g.attributes.position};}
    const rainField=weatherField(84,0x66bde3,.017),snowField=weatherField(52,0xd4efff,.026),windField=weatherField(38,0x8dbbd3,.014),heatField=weatherField(26,0xffb36a,.022);
    let doorOpen=0,carPresence=1,carStateReady=false,tvLevel=0,ledLevel=0,alarmLevel=0,focusLevel=0,focusState='IDLE',cameraReady=false;
    const focusTarget=new THREE.Vector3(1.25,1.08,.95),focusCamera=new THREE.Vector3(),idleCamera=new THREE.Vector3();
    // Thermal scale: cool blue begins at 16°C, a readable light blue sits at
    // 18°C, then the floors move through warm tones to deep red at 26°C.
    const thermalStops=[[16,0x155ab6],[18,0x9be6ff],[20,0x45bce8],[21,0xff7600],[22,0xff1800],[24,0xc90008],[26,0x700008]];
    function thermalColour(value){const t=clamp(Number(value),16,26);for(let i=1;i<thermalStops.length;i++){if(t<=thermalStops[i][0]){const a=thermalStops[i-1],b=thermalStops[i],f=(t-a[0])/(b[0]-a[0]);return new THREE.Color(a[1]).lerp(new THREE.Color(b[1]),f);}}return new THREE.Color(thermalStops[thermalStops.length-1][1]);}
    function setFixture(name,on,intensity=1){const f=fixtures[name];if(!f)return;f.level+=((on?intensity:0)-f.level)*.11;f.mat.emissiveIntensity=.02+f.level*.78;f.pool.intensity=f.level*.72;}
    function setThermal(name,value){const zone=roomZones[name];if(!zone)return;const valid=num(value),target=valid?thermalColour(value):new THREE.Color(0x0b5270);zone.material.color.lerp(target,.07);zone.material.emissive.lerp(target,.05);const opacity=valid?.075:.035;zone.material.opacity+=(opacity-zone.material.opacity)*.07;}
    // The floor slabs themselves carry the two real floor temperatures.
    // This keeps thermal information architectural and permanently readable
    // without introducing numeric labels or solid colour blocks.
    function setFloorThermal(floor,value,base){
      const valid=num(value),thermal=valid?thermalColour(value):base.clone();
      // Let the measured colour own the plane. The opacity/intensity ease so
      // a changed sensor reads as physical thermal light, never a hard flash.
      const target=base.clone().lerp(thermal,valid?.88:0);
      floor.material.color.lerp(target,.075);
      floor.material.opacity+=( (valid?.40:.14)-floor.material.opacity)*.07;
    }
    return {frame(now){
      if(now-received>30)state={};
      const tuning=state._tuning||{};
      const tune=(key,fallback)=>Number.isFinite(Number(tuning[key]))?Number(tuning[key]):fallback;
      const rooms=state.rooms||{},wattsNow=Number(state.watts_now),exporting=num(wattsNow)&&wattsNow<0,chargerLoad=num(wattsNow)&&wattsNow>6000;
      const solarPower=exporting?clamp(Math.abs(wattsNow)/2800,0,1):0;
      panels.forEach(m=>{m.material.emissiveIntensity=.1+solarPower*.42;m.material.color.setHSL(.61,.84,.16+solarPower*.07);});
      windows.forEach(w=>{const lit=rooms[w.room]&&rooms[w.room].light===true;w.m.material.color.setHex(lit?0x7a3f14:0x0c496a);w.m.material.emissive.setHex(lit?0xc05a12:0x08263b);w.m.material.emissiveIntensity=lit?.32+.06*Math.sin(now*1.2):.12;});
      const living=rooms.livingroom||{},bedroom=rooms.bedroom||{},upstairs=rooms.upstairs||{};
      setFixture('porch',rooms.porch&&rooms.porch.light===true);setFixture('hallway',rooms.hallway&&rooms.hallway.light===true);
      setFixture('bedroom1',rooms.bedroom1&&rooms.bedroom1.light===true || bedroom.light===true);setFixture('bedroom2',rooms.bedroom2&&rooms.bedroom2.light===true || upstairs.light===true);setFixture('bedroom3',rooms.bedroom3&&rooms.bedroom3.light===true || upstairs.light===true);setFixture('bathroom',rooms.bathroom&&rooms.bathroom.light===true);
      setFixture('livingroom',living.light===true);for(const n of ['spot1','spot2','spot3'])setFixture(n,living.spotlights===true,.78);
      amber.intensity=living.light===true?.28:.02;
      ledLevel+=((living.led===true?1:0)-ledLevel)*.10;ledStrip.material.emissiveIntensity=.04+ledLevel*.72;
      const devices=state.devices||{};tvLevel+=((devices.tv===true?1:0)-tvLevel)*.09;tvScreen.material.emissiveIntensity=.03+tvLevel*.62;tvGlow.intensity=tvLevel*.36;
      doorOpen+=((devices.front_door_open===true?1:0)-doorOpen)*.08;doorPivot.rotation.y=-doorOpen*.95;
      const alarm=String(devices.alarm||''),triggered=/trigger|alarm/.test(alarm),armed=/armed/.test(alarm),alarmColour=triggered?0xf0352e:(armed?0xffaa55:0x3f8fb1),alarmTarget=triggered?1:(armed?.45:0);
      alarmLevel+=(alarmTarget-alarmLevel)*.1;alarmBox.material.emissive.setHex(alarmColour);alarmBox.material.emissiveIntensity=.08+alarmLevel*.8;alarmLed.material.color.setHex(alarmColour);alarmLed.material.opacity=.22+alarmLevel*.7;
      // Open curtains are not merely transparent: they are hidden entirely.
      // On a state change the two physical panels ease from the side returns
      // to their respective halves of the window, then reverse and vanish
      // once the real curtain has fully opened.
      const openTarget=curtainState.known?curtainState.target:1;
      const curtainDt=curtainState.lastAt===null?0:clamp(now-curtainState.lastAt,0,.12);
      curtainState.lastAt=now;
      // Time-based easing keeps the motion calm on a Pi without becoming a
      // different speed at a lower frame rate (about 2.5s to settle).
      curtainState.open+=(openTarget-curtainState.open)*(1-Math.exp(-curtainDt/.8));
      const closed=1-curtainState.open;
      // Curtains exist only inside the living-room window (glass x -.33..0.69):
      // each panel is drawn from its outer frame edge toward the centre, and
      // there is nothing to see when they are open - never a panel outside
      // the frame reading as an exterior shutter.
      const drawn=Math.max(closed,.001);
      curtains[0].scale.x=curtains[1].scale.x=drawn;
      curtains[0].position.x=-.33+.255*drawn;
      curtains[1].position.x=.69-.255*drawn;
      curtains[0].visible=curtains[1].visible=closed>.004;
      const downTemp=rooms.downstairs&&rooms.downstairs.temperature_c,upTemp=upstairs.temperature_c;
      for(const name of ['hallway','livingroom','kitchen'])setThermal(name,(rooms[name]&&rooms[name].temperature_c)||downTemp);
      for(const name of ['bedroom1','bedroom2','bedroom3','bathroom'])setThermal(name,(rooms[name]&&rooms[name].temperature_c)||upTemp);
      setFloorThermal(groundFloor,downTemp,new THREE.Color(0x0a4058));
      setFloorThermal(upperFloor,upTemp,new THREE.Color(0x0b4a63));
      carChargeLed.material.opacity=0;chargerLed.material.color.setHex(chargerLoad?0xff9b4a:0x48bddd);chargerLed.material.opacity=chargerLoad?.65:.3;chargerFace.material.emissive.setHex(chargerLoad?0x9a4b16:0x082d3d);chargerFace.material.emissiveIntensity=chargerLoad?.65:.18;
      // Presence drives an understated driveway arrival/departure rather than
      // an abrupt visibility toggle.  The first live state is adopted
      // directly, so a page opened while the car is away never plays a fake
      // departure animation.
      const carTarget=devices.car_present===false?0:1;
      if(!carStateReady){carPresence=carTarget;carStateReady=true;}
      else carPresence+=(carTarget-carPresence)*.018;
      car.visible=carTarget>0||carPresence>.012;
      car.position.z=.34+(1-carPresence)*1.45;
      car.scale.x=car.scale.z=.88+carPresence*.12;
      const cameras=state.cameras||{},porchActive=rooms.porch&&rooms.porch.occupied===true,externalActive=rooms.external&&rooms.external.occupied===true;
      doorbellLens.material.color.setHex(porchActive?0xffa34a:0x285b72);doorbellLens.material.opacity=porchActive?.7+.15*Math.sin(now*5):(cameras.doorbell ? .5 : .28);
      cameraLens.material.color.setHex(externalActive?0xffa34a:0x285b72);cameraLens.material.opacity=externalActive?.7+.15*Math.sin(now*5.3):(cameras.external ? .5 : .28);
      for(const name of Object.keys(figures)){const f=figures[name],active=rooms[name]&&rooms[name].occupied===true;f.level+=((active?1:0)-f.level)*.12;f.mat.opacity=f.level*.58;}
      holoPoints.material.opacity=.14;
      const weather=state.weather||{},rain=Number(weather.rain_mm_h),snow=Number(weather.snow_mm_h),wind=Number(weather.wind_mph),outsideTemp=Number(weather.temperature_c),condition=String(weather.condition||'').toLowerCase();
      // Actual sunrise/sunset-derived state subtly shifts the model's
      // ambience; it never adds a clock, label, or guessed night mode.
      const night=weather.is_night===true;
      hemi.intensity+=( (night?.15:.26)-hemi.intensity)*.025;
      key.intensity+=( (night?.38:.68)-key.intensity)*.025;
      rim.intensity+=( (night?.34:.24)-rim.intensity)*.025;
      const heavyRain=num(rain)&&rain>=4, snowfall=num(snow)&&snow>0&&condition.includes('snow'), strongWind=num(wind)&&wind>=40, highHeat=num(outsideTemp)&&outsideTemp>=28;
      const rainStrength=heavyRain?clamp((rain-4)/8,0,1):0;
      const snowStrength=snowfall?clamp(snow/5,0,1):0;
      const windStrength=strongWind?clamp((wind-40)/40,0,1):0;
      const heatStrength=highHeat?clamp((outsideTemp-28)/8,0,1):0;
      function weatherVisible(field,on,opacity,fall,drift=0){field.mesh.material.opacity=on?opacity:0;if(!on)return;const a=field.attr.array;for(let i=0;i<a.length;i+=3){a[i]=field.base[i]+(((now*drift+i*.07)%1)-.5)*.45;a[i+1]=field.base[i+1]-((now*fall+i*.037)%3.2);a[i+2]=field.base[i+2]+(((now*drift+i*.11)%1)-.5)*.2;}field.attr.needsUpdate=true;}
      weatherVisible(rainField,heavyRain,.40+rainStrength*.28,1.05+rainStrength*.7,strongWind?.18+windStrength*.28:.05);
      weatherVisible(snowField,snowfall,.38+snowStrength*.28,.10+snowStrength*.14,strongWind?.06+windStrength*.18:.025);
      weatherVisible(windField,strongWind&&!heavyRain&&!snowfall,.13+windStrength*.16,.025,.28+windStrength*.30);
      weatherVisible(heatField,highHeat,.10+heatStrength*.12,-.02-heatStrength*.025,.06+heatStrength*.05);
      // Camera director: an eased 90-degree front-side idle orbit, overridden
      // by real motion/alarm events.  It manipulates this Three camera only.
      let wanted=null;
      if(triggered)wanted=[.92,1.35,D];
      else if(porchActive)wanted=[1.93,.45,2.0];
      else if(externalActive)wanted=[1.42,.35,2.06];
      else if(now<curtainState.eventUntil)wanted=roomAnchors.livingroom;
      else if(living.occupied===true)wanted=roomAnchors.livingroom;
      else if(rooms.bedroom&&rooms.bedroom.occupied===true)wanted=roomAnchors.bedroom1;
      else if(upstairs.occupied===true)wanted=roomAnchors.bedroom2;
      const targetFocus=!!wanted;focusLevel+=((targetFocus?1:0)-focusLevel)*.07;
      focusState=targetFocus?(focusLevel<.96?'TRANSITION_IN':'FOCUS'):(focusLevel>.04?'TRANSITION_OUT':'IDLE');
      document.documentElement.style.setProperty('--twin-focus',focusLevel.toFixed(3));
      // During a real event, let the transparent architecture reveal the
      // active zone instead of overlaying explanatory UI.
      steel.opacity=.25-focusLevel*.11;roofMat.opacity=.34-focusLevel*.12;wallInset.opacity=.28-focusLevel*.10;
      // A complete, front-side 90-degree idle orbit: pause at each end,
      // ease across, then reverse. The steady animation clock keeps it
      // independent of the 80-second panel scheduler, so it never snaps
      // back when the mirror timeline restarts.
      const pause=tune('home_orbit_pause',7),travel=tune('home_orbit_seconds',54),orbitCycle=(pause+travel)*2;
      const orbitAt=now%orbitCycle;
      let orbitSide;
      if(orbitAt<pause) orbitSide=-1;
      else if(orbitAt<pause+travel){const x=(orbitAt-pause)/travel;orbitSide=-Math.cos(Math.PI*x);}
      else if(orbitAt<pause+travel+pause) orbitSide=1;
      else {const x=(orbitAt-pause-travel-pause)/travel;orbitSide=Math.cos(Math.PI*x);}
      const azimuth=orbitSide*(Math.PI*tune('home_orbit_angle',45)/180),radius=tune('home_camera_radius',6.0);
      const idleTarget=new THREE.Vector3(tune('home_target_x',1.25),tune('home_target_y',1.08),tune('home_target_z',.95));
      idleCamera.set(idleTarget.x+Math.sin(azimuth)*radius,tune('home_camera_height',4.25),idleTarget.z+Math.cos(azimuth)*radius);
      if(wanted)focusTarget.lerp(new THREE.Vector3(...wanted),.11);else focusTarget.lerp(idleTarget,.055);
      // Approximately a 2x apparent-size inspection, rather than an
      // extreme crop that obscures the location of the event.
      focusCamera.copy(idleCamera).sub(focusTarget).normalize().multiplyScalar(4.7).add(focusTarget);focusCamera.y=Math.max(focusCamera.y,focusTarget.y+1.35);
      // A newly mounted panel used to start at a fixed left-front camera,
      // then lerp toward whatever global clock phase happened to be current.
      // That made its first rendered frames look like a whip-pan.  Adopt the
      // current orbit position once, then interpolate only between adjacent
      // orbit frames.
      if(!cameraReady){camera.position.copy(idleCamera);camera.lookAt(focusTarget);cameraReady=true;}
      camera.position.lerp(idleCamera,.08).lerp(focusCamera,focusLevel);camera.lookAt(focusTarget);
      const fov=tune('home_camera_fov',33)-focusLevel*6;if(Math.abs(camera.fov-fov)>.02){camera.fov=fov;camera.updateProjectionMatrix();}
      renderer.toneMappingExposure=1.05*tune('home_brightness',1.0);
      el.style.setProperty('--twin-stage-scale',tune('home_stage_scale',1.0).toFixed(3));
      el.style.setProperty('--twin-x',tune('home_x',0).toFixed(1)+'px');
      el.style.setProperty('--twin-y',tune('home_y',0).toFixed(1)+'px');
      home.rotation.y=-.16;home.position.y=0;renderer.render(scene,camera);
    },dispose(){renderer.dispose();canvas.remove();}};
  }
  function render(){return '';} // no SVG fallback: the house is a WebGL scene.
  function mount(el){
    let fx;
    const frame=now=>{if(!fx)fx=buildScene(el);if(fx)fx.frame(now);};
    // Panels are refreshed from live state. Explicit disposal is essential on
    // Chromium/Pi: removing a canvas alone does not release its WebGL context.
    frame.dispose=()=>{if(fx){fx.dispose();fx=null;}};
    return frame;
  }
  return {update,setTuning,render,mount};
})();
