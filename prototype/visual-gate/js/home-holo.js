/* The hologram house: the real home as light, drawn on the shared stage.

   ARCHITECTURE IS NOT AUTHORED HERE. Every solid below is built with the
   same code and the same coordinates as the classic renderer
   (js/home-twin.js, frozen); only materials and effects differ. The
   architecture lock (node test_house_layout.js --holo) proves every
   classic solid exists here in exactly the same place. If a coordinate
   needs to change, it changes in both files and the owner signs it off.

   What is new relative to the classic:
     - shell: unlit Fresnel glass - faces nearly transparent, silhouettes
       lit - with faint rising scan lines; it reads as light shaped like a
       house rather than a translucent plastic model
     - no hard crop: drawn on the stage with a generous margin and a
       feathered edge, so the car and ground fade instead of being cut
     - lit rooms fill with warm volumetric light and pool on the floor
     - energy as particles along real routes, speed and density from the
       real watts, direction from the real sign of the grid flow
     - weather with weight: rain streaks slanted by the real wind, snow,
       storm lightning that lights the whole model - same thresholds
     - presence: a few hundred anonymous points that assemble, breathe
       and dissolve, still plainly approximate
     - a build-in when the house arrives (points of light rise up the
       walls) and a slow scan pass through it every 40 s at rest

   The presentation is mirrored like the classic's CSS scaleX(-1), but by
   negating x in the projection. Every material here is double-sided, so
   the flipped winding cannot cull anything. */

const HomeHolo = (() => {
  'use strict';
  const W=2.5,X0=-.5,MAIN_W=W-X0,MAIN_C=(W+X0)/2,GARAGE_W=.77*1.15,GARAGE_C=W+(.77*1.15)/2,GARAGE_X=W+.77*1.15,D=1.65,H=1.65,RIDGE=2.23;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  const GLOW=1;
  const MARGIN=170;          // stage px added round the classic canvas box
  let state={}, received=-Infinity;
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
  function setTuning(tuning) { state=Object.assign({},state,{_tuning:tuning||{}}); }

  // ------------------------------------------------------------ materials

  const HOLO_VERT = `
    varying vec3 vN; varying vec3 vV; varying vec3 vW;
    void main(){
      vec4 w = modelMatrix * vec4(position,1.0);
      vW = w.xyz;
      vec4 mv = viewMatrix * w;
      vN = normalize(normalMatrix * normal);
      vV = -mv.xyz;
      gl_Position = projectionMatrix * mv;
    }`;
  // Shared uniforms (one object, referenced by every holo material) carry
  // the house-wide state: fade, build-in, time, scan pass, flash, gain.
  const shared = {
    uFade:{value:1}, uBuild:{value:1}, uTime:{value:0}, uPass:{value:-10},
    uFlash:{value:0}, uGain:{value:1}, uFocus:{value:0},
  };
  const HOLO_FRAG = `
    uniform vec3 uColor; uniform float uBase; uniform float uRim; uniform float uScan;
    uniform float uLevel; uniform vec3 uLitColor; uniform float uShell;
    uniform float uFade; uniform float uBuild; uniform float uTime; uniform float uPass;
    uniform float uFlash; uniform float uGain; uniform float uFocus;
    varying vec3 vN; varying vec3 vV; varying vec3 vW;
    void main(){
      // Build-in: the model assembles from the ground up, led by a bright seam.
      float reveal = uBuild * 3.4 - 0.25;
      if (vW.y > reveal) discard;
      float seam = (1.0 - smoothstep(0.0, 0.10, reveal - vW.y)) * step(uBuild, 0.999);
      float ndv = abs(dot(normalize(vN), normalize(vV)));
      float rim = pow(1.0 - ndv, 2.3);
      float line = 1.0 - smoothstep(0.0, 0.07, fract(vW.y * 15.0 - uTime * 0.18));
      float pass = exp(-pow((vW.y - uPass) * 9.0, 2.0));
      // Event focus thins the shell so the affected room reads through it.
      float shell = mix(1.0, 0.55, uFocus * uShell);
      vec3 col = mix(uColor, uLitColor, uLevel);
      float a = (uBase + uRim * rim + uScan * line) * shell + uLevel * (0.16 + 0.24 * rim);
      a += pass * 0.35 + seam * 0.9 + uFlash * (0.25 + rim);
      a *= uFade * uGain;
      gl_FragColor = vec4(col + seam * vec3(0.5, 0.8, 1.0), clamp(a, 0.0, 1.0));
    }`;

  function holo(colour, o={}) {
    const u = Object.assign({
      uColor:{value:new THREE.Color(colour)}, uBase:{value:o.base??.025}, uRim:{value:o.rim??.55},
      uScan:{value:o.scan??.05}, uLevel:{value:0}, uLitColor:{value:new THREE.Color(o.lit??0xffae52)},
      uShell:{value:o.shell??1},
    }, shared);
    return new THREE.ShaderMaterial({vertexShader:HOLO_VERT, fragmentShader:HOLO_FRAG, uniforms:u,
      transparent:true, depthWrite:false, side:THREE.DoubleSide, blending:THREE.AdditiveBlending});
  }

  // Soft round point sprites with per-point alpha: energy, presence, snow.
  const POINT_VERT = `
    attribute float aAlpha; varying float vA;
    uniform float uSize; uniform float uScale;
    void main(){
      vA = aAlpha;
      vec4 mv = modelViewMatrix * vec4(position,1.0);
      gl_PointSize = uSize * uScale / max(0.1, -mv.z);
      gl_Position = projectionMatrix * mv;
    }`;
  const POINT_FRAG = `
    uniform vec3 uColor; uniform float uFade; uniform float uGain; varying float vA;
    void main(){
      vec2 d = gl_PointCoord - 0.5; float r = dot(d,d) * 4.0;
      float a = exp(-r * 3.0) * vA * uFade * uGain;
      if (a < 0.004) discard;
      gl_FragColor = vec4(uColor, a);
    }`;
  const pointScale = {value:600};
  function pointsMaterial(colour, size) {
    return new THREE.ShaderMaterial({vertexShader:POINT_VERT, fragmentShader:POINT_FRAG,
      uniforms:{uColor:{value:new THREE.Color(colour)}, uSize:{value:size}, uScale:pointScale,
        uFade:shared.uFade, uGain:shared.uGain},
      transparent:true, depthWrite:false, blending:THREE.AdditiveBlending});
  }
  function pointCloud(count, colour, size, parent) {
    const g=new THREE.BufferGeometry();
    g.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(count*3),3));
    g.setAttribute('aAlpha',new THREE.Float32BufferAttribute(new Float32Array(count),1));
    const p=new THREE.Points(g,pointsMaterial(colour,size));p.frustumCulled=false;p.layers.enable(GLOW);parent.add(p);
    return {points:p,pos:g.attributes.position,alpha:g.attributes.aAlpha,count};
  }

  // A radial glow texture drawn once, for room light volumes and pools.
  let glowTex=null;
  function glowTexture(){
    if(glowTex)return glowTex;
    const c=document.createElement('canvas');c.width=c.height=64;
    const x=c.getContext&&c.getContext('2d');
    if(x){const g=x.createRadialGradient(32,32,0,32,32,32);g.addColorStop(0,'rgba(255,255,255,1)');g.addColorStop(.35,'rgba(255,255,255,.45)');g.addColorStop(1,'rgba(255,255,255,0)');x.fillStyle=g;x.fillRect(0,0,64,64);}
    glowTex=new THREE.CanvasTexture(c);return glowTex;
  }

  // Deterministic hash, so captures repeat.
  const hash=(n)=>{const s=Math.sin(n*127.1+311.7)*43758.5453;return s-Math.floor(s);};

  // ------------------------------------------------------------ scene

  function build(opts={}) {
    const scene=new THREE.Scene();
    const camera=new THREE.PerspectiveCamera(33,1100/680,.1,30);camera.position.set(-5.1,4.25,6.5);camera.lookAt(1.25,1.08,.95);
    const home=new THREE.Group();scene.add(home);scene.userData.home=home;
    home.scale.y=1.2;

    const shellCol=0x3fb6e6;
    const steel=holo(shellCol,{base:.02,rim:.55,scan:.05});
    const wallInset=holo(shellCol,{base:.03,rim:.25,scan:0});
    const roofMat=holo(0x4cc6f0,{base:.03,rim:.5,scan:.04});
    const edgeMat=new THREE.LineBasicMaterial({color:0x7fd6ff,transparent:true,opacity:.5,blending:THREE.AdditiveBlending,depthWrite:false});
    const solar=holo(0x1f5cff,{base:.10,rim:.35,scan:0,shell:0,lit:0x6fc0ff});
    const dark=holo(0x2a6f8f,{base:.03,rim:.4,scan:0});
    // One shared material for the small fixed housings, so they merge.
    const deviceShared=holo(0x57c3ea,{base:.05,rim:.45,scan:0,shell:0});
    const deviceMat=()=>deviceShared;

    // Silhouette and major creases only - never an edge on every box.
    function silhouette(mesh,angle=35){const l=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry,angle),edgeMat);l.position.copy(mesh.position);l.rotation.copy(mesh.rotation);l.layers.enable(GLOW);home.add(l);return l;}
    function quad(a,b,c,d,material){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute([...a,...b,...c,...d],3));g.setIndex([0,1,2,0,2,3]);g.computeVertexNormals();return new THREE.Mesh(g,material);}
    function taperedCabin(material){const g=new THREE.BufferGeometry();const p=[-.36,0,-.23,.36,0,-.23,.36,0,.23,-.36,0,.23,-.23,.25,-.17,.21,.25,-.17,.21,.25,.17,-.23,.25,.17];g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));g.setIndex([0,1,2,0,2,3,4,6,5,4,7,6,0,4,5,0,5,1,1,5,6,1,6,2,2,6,7,2,7,3,3,7,4,3,4,0]);g.computeVertexNormals();return new THREE.Mesh(g,material);}
    function box(w,h,d,mat,x,y,z,outlined=false){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat);m.position.set(x,y,z);home.add(m);if(outlined)silhouette(m);return m;}

    // --- architecture: identical to the classic renderer ---
    const mainBox=box(MAIN_W,H,D,steel,MAIN_C,H/2,D/2);silhouette(mainBox);
    const frontRoof=quad([X0,H,D],[W,H,D],[1.96,RIDGE,D/2],[X0,RIDGE,D/2],roofMat);home.add(frontRoof);
    const backRoof=quad([X0,H,0],[W,H,0],[1.96,RIDGE,D/2],[X0,RIDGE,D/2],roofMat);home.add(backRoof);
    const hipRoof=quad([W,H,0],[W,H,D],[1.96,RIDGE,D/2],[1.96,RIDGE,D/2],roofMat);home.add(hipRoof);
    [frontRoof,backRoof,hipRoof].forEach(m=>silhouette(m));
    box(.25,.46,.19,deviceMat(),.445,2.35,.815,true);
    const garage=box(GARAGE_W,.71,1.67,holo(shellCol,{base:.025,rim:.5,scan:.04}),GARAGE_C,.355,1.035);silhouette(garage);
    const gRoof=quad([W,.89,.20],[GARAGE_X,.71,.20],[GARAGE_X,.71,1.87],[W,.89,1.87],roofMat);home.add(gRoof);silhouette(gRoof);
    const porch=box(.702,.72,.32,holo(shellCol,{base:.03,rim:.5,scan:.04}),1.93,.36,1.81);silhouette(porch);
    const pRoof=quad([1.539,.84,D],[2.321,.84,D],[2.321,.75,2.01],[1.539,.75,2.01],roofMat);home.add(pRoof);
    const fascia=holo(0x6fcff5,{base:.08,rim:.4,scan:0});
    function trim(w,h,d,x,y,z){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),fascia);m.position.set(x,y,z);home.add(m);}
    trim(MAIN_W+.08,.055,.07,MAIN_C,H,D+.025);trim(.07,.055,D+.08,W+.025,H,D/2);trim(.07,.055,D+.08,X0-.025,H,D/2);trim(.08,.06,.08,1.96,RIDGE,D/2);

    // Thermal floors keep the classic's measured colours on plain blending,
    // so 22°C stays readable as red rather than being washed out.
    const floorMat=new THREE.MeshBasicMaterial({color:0x0a4058,transparent:true,opacity:.14,depthWrite:false,side:THREE.DoubleSide});
    const upperFloorMat=floorMat.clone();upperFloorMat.color.setHex(0x0b4a63);
    function innerFrame(w,d,y){const g=new THREE.EdgesGeometry(new THREE.BoxGeometry(w,.028,d));const l=new THREE.LineSegments(g,new THREE.LineBasicMaterial({color:0x4db6de,transparent:true,opacity:.38,blending:THREE.AdditiveBlending,depthWrite:false}));l.position.set(MAIN_C,y,D/2);home.add(l);}
    const upperFloor=box(2.78,.025,1.48,upperFloorMat,1.00,.87,.825);
    const groundFloor=box(2.92,.024,1.58,floorMat,1.00,.10,.825);innerFrame(2.92,1.58,.10);
    const roomAnchors={hallway:[2.02,.43,.83],livingroom:[.90,.43,1.24],kitchen:[.90,.43,.40],bedroom1:[.44,1.20,1.24],bedroom2:[1.82,1.20,1.24],bedroom3:[.44,1.20,.40],bathroom:[1.82,1.20,.40]};
    const roomZones={};
    function roomZone(name,w,d,x,y,z){const mat=new THREE.MeshBasicMaterial({color:0x0b5270,transparent:true,opacity:.035,depthWrite:false,side:THREE.DoubleSide});const m=new THREE.Mesh(new THREE.PlaneGeometry(w,d),mat);m.rotation.x=-Math.PI/2;m.position.set(x,y,z);m.name='zone-'+name;home.add(m);roomZones[name]=m;}
    roomZone('hallway',.68,1.52,2.02,.055,.825);roomZone('livingroom',1.48,.72,.90,.055,1.19);roomZone('kitchen',1.48,.72,.90,.055,.46);
    roomZone('bedroom1',1.58,.66,.44,.825,1.18);roomZone('bedroom2',1.02,.66,1.86,.825,1.18);roomZone('bedroom3',1.58,.66,.44,.825,.47);roomZone('bathroom',1.02,.66,1.86,.825,.47);
    const planMat=new THREE.LineBasicMaterial({color:0x52b7dc,transparent:true,opacity:.42,depthWrite:false,blending:THREE.AdditiveBlending});
    function planBoundaries(y,segments){const v=[];segments.forEach(s=>v.push(s[0],y,s[1],s[2],y,s[3]));const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(v,3));home.add(new THREE.LineSegments(g,planMat));}
    planBoundaries(.06,[[1.68,.04,1.68,1.61],[-.46,.825,1.68,.825]]);
    planBoundaries(.835,[[1.25,.13,1.25,1.52],[-.36,.825,2.36,.825]]);

    const windows=[];
    const frameMat=holo(0x8fdcff,{base:.06,rim:.35,scan:0,shell:0});
    function window(w,h,x,y,z,room){
      const recess=new THREE.Mesh(new THREE.PlaneGeometry(w+.12,h+.12),wallInset);recess.position.set(x,y,z-.01);home.add(recess);
      // Each pane owns its uniforms: a cloned ShaderMaterial deep-copies them,
      // which would detach it from the house-wide shared state.
      const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),holo(0x5fc8f5,{base:.05,rim:.3,scan:0,shell:0}));m.position.set(x,y,z+.012);m.layers.enable(GLOW);windows.push({m,room});home.add(m);
      const frame=.021,lip=.024;
      for(const [fw,fh,fx,fy] of [[w+.08,frame,x,y+h/2+lip],[w+.08,frame,x,y-h/2-lip],[frame,h+.08,x-w/2-lip,y],[frame,h+.08,x+w/2+lip,y]]){const f=new THREE.Mesh(new THREE.BoxGeometry(fw,fh,.05),frameMat);f.position.set(fx,fy,z+.02);home.add(f);}
      return m;
    }
    window(.84,.352,.10,1.284,D+.012,'bedroom');window(.64,.352,1.74,1.284,D+.013,'upstairs');window(1.02,.42,.18,.49,D+.014,'livingroom');
    const door=window(.34,.54,1.93,.36,2.013,'door');door.material.uniforms.uColor.value.setHex(0x3a9ccf);door.material.uniforms.uBase.value=.12;
    home.remove(door);
    const doorPivot=new THREE.Group();doorPivot.position.set(1.76,.36,2.025);door.position.set(.17,0,0);doorPivot.add(door);home.add(doorPivot);
    window(.13,.27,1.66,.50,2.014,'porch');window(.13,.27,2.20,.50,2.014,'porch');

    const doorbell=new THREE.Group();home.add(doorbell);
    const doorbellBody=new THREE.Mesh(new THREE.BoxGeometry(.065,.17,.034),deviceMat());doorbellBody.position.set(1.79,.43,2.035);doorbell.add(doorbellBody);
    const doorbellLens=new THREE.Mesh(new THREE.SphereGeometry(.019,10,8),new THREE.MeshBasicMaterial({color:0x285b72,transparent:true,opacity:.5,blending:THREE.AdditiveBlending,depthWrite:false}));doorbellLens.position.set(1.79,.47,2.06);doorbellLens.layers.enable(GLOW);doorbell.add(doorbellLens);
    const frontCamera=new THREE.Group();home.add(frontCamera);
    const cameraMount=new THREE.Mesh(new THREE.CylinderGeometry(.026,.026,.13,10),deviceMat());cameraMount.rotation.x=Math.PI/2;cameraMount.position.set(1.86,.96,1.98);frontCamera.add(cameraMount);
    const cameraBody=new THREE.Mesh(new THREE.BoxGeometry(.13,.075,.085),deviceMat());cameraBody.position.set(1.86,.98,2.04);frontCamera.add(cameraBody);
    const cameraLens=new THREE.Mesh(new THREE.SphereGeometry(.026,10,8),new THREE.MeshBasicMaterial({color:0x285b72,transparent:true,opacity:.5,blending:THREE.AdditiveBlending,depthWrite:false}));cameraLens.position.set(1.86,.98,2.093);cameraLens.layers.enable(GLOW);frontCamera.add(cameraLens);
    const curtainMat=holo(0x9aa8ff,{base:.16,rim:.35,scan:0,shell:0});
    const curtains=[new THREE.Mesh(new THREE.BoxGeometry(.51,.43,.025),curtainMat),new THREE.Mesh(new THREE.BoxGeometry(.51,.43,.025),curtainMat)];
    curtains.forEach(m=>{m.position.set(.18,.49,D+.03);home.add(m);});
    const garageDoor=new THREE.Mesh(new THREE.PlaneGeometry(.667,.52),wallInset);garageDoor.position.set(GARAGE_C,.34,1.873);home.add(garageDoor);
    const slatMat=holo(0x6fcff5,{base:.07,rim:.3,scan:0,shell:0});
    for(let y=.13;y<.58;y+=.09){const slat=new THREE.Mesh(new THREE.BoxGeometry(.677,.018,.028),slatMat);slat.position.set(GARAGE_C,y,1.886);home.add(slat);}

    const panels=[];const roof=(x,u)=>[x,H+(RIDGE-H)*u,D-u*D/2];
    const mix=(a,b,t)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,a[2]+(b[2]-a[2])*t];
    const cellMat=new THREE.LineBasicMaterial({color:0x6fb8ff,transparent:true,opacity:.35,blending:THREE.AdditiveBlending,depthWrite:false});
    for(let r=0;r<2;r++)for(let c=0;c<4;c++){
      const x0=.16+c*.29,x1=x0+.26,u0=.16+r*.26,u1=u0+.24,a=roof(x0,u0),b=roof(x1,u0),cc=roof(x1,u1),d=roof(x0,u1);
      const m=quad(a,b,cc,d,solar);m.layers.enable(GLOW);home.add(m);panels.push(m);
      const cell=new THREE.BufferGeometry(),lines=[];
      for(let i=1;i<3;i++){lines.push(...mix(a,b,i/3),...mix(d,cc,i/3));}
      for(let i=1;i<3;i++){lines.push(...mix(a,d,i/3),...mix(b,cc,i/3));}
      cell.setAttribute('position',new THREE.Float32BufferAttribute(lines,3));home.add(new THREE.LineSegments(cell,cellMat));
    }
    const roofCentre=roof(.73,.4);

    const car=new THREE.Group();car.position.z=.34;car.scale.y=1/1.2;home.add(car);
    const carPaint=holo(0x5fb8e0,{base:.03,rim:.6,scan:.03,lit:0xffd060});
    const carBody=new THREE.Mesh(new THREE.BoxGeometry(1.3,.16,.5),carPaint);carBody.position.set(.78,.22,2.24);car.add(carBody);
    const bonnet=new THREE.Mesh(new THREE.BoxGeometry(.43,.08,.47),carPaint);bonnet.position.set(1.2,.34,2.24);car.add(bonnet);
    const rear=new THREE.Mesh(new THREE.BoxGeometry(.22,.07,.47),carPaint);rear.position.set(.24,.32,2.24);car.add(rear);
    const cabin=taperedCabin(carPaint);cabin.position.set(.75,.31,2.24);car.add(cabin);
    const hardRoof=new THREE.Mesh(new THREE.BoxGeometry(.42,.045,.36),carPaint);hardRoof.position.set(.75,.57,2.24);car.add(hardRoof);
    const autoGlass=holo(0x3d8fbf,{base:.08,rim:.3,scan:0,shell:0});
    const windscreen=new THREE.Mesh(new THREE.PlaneGeometry(.36,.19),autoGlass);windscreen.rotation.y=Math.PI/2;windscreen.rotation.z=-.16;windscreen.position.set(1.105,.45,2.24);car.add(windscreen);
    const rearScreen=new THREE.Mesh(new THREE.PlaneGeometry(.36,.17),autoGlass);rearScreen.rotation.y=Math.PI/2;rearScreen.rotation.z=.18;rearScreen.position.set(.395,.45,2.24);car.add(rearScreen);
    for(const x of [.35,1.2])for(const z of [2.01,2.47]){const tyre=new THREE.Mesh(new THREE.CylinderGeometry(.125,.125,.07,14),dark);tyre.rotation.x=Math.PI/2;tyre.position.set(x,.13,z);car.add(tyre);const hub=new THREE.Mesh(new THREE.CylinderGeometry(.052,.052,.074,12),dark);hub.rotation.x=Math.PI/2;hub.position.set(x,.13,z);car.add(hub);}
    const carChargeLed=new THREE.Mesh(new THREE.SphereGeometry(.025,10,8),new THREE.MeshBasicMaterial({color:0xffd060,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false}));carChargeLed.position.set(.16,.25,2.48);carChargeLed.layers.enable(GLOW);car.add(carChargeLed);
    [carBody,cabin].forEach(m=>{const l=new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry,35),edgeMat);l.position.copy(m.position);car.add(l);});

    const charger=new THREE.Group();home.add(charger);
    const chargerBody=new THREE.Mesh(new THREE.BoxGeometry(.05,.22,.13),deviceMat());chargerBody.position.set(1.505,.40,1.83);charger.add(chargerBody);
    const chargerFace=new THREE.Mesh(new THREE.PlaneGeometry(.095,.16),holo(0x48bddd,{base:.1,rim:.3,scan:0,shell:0,lit:0xffb24a}));chargerFace.rotation.y=-Math.PI/2;chargerFace.position.set(1.477,.40,1.83);chargerFace.layers.enable(GLOW);charger.add(chargerFace);
    const chargerLed=new THREE.Mesh(new THREE.SphereGeometry(.014,8,6),new THREE.MeshBasicMaterial({color:0x48bddd,transparent:true,opacity:.3,blending:THREE.AdditiveBlending,depthWrite:false}));chargerLed.position.set(1.47,.43,1.83);chargerLed.layers.enable(GLOW);charger.add(chargerLed);

    // Real-light fixtures: the same few, now each with a warm light volume
    // filling its space and a pool on the floor beneath it.
    const fixtures={};
    function fixture(name,x,y,z,colour=0xffa34a,distance=.8,floorY=null){
      const mat=holo(0x6a8796,{base:.08,rim:.3,scan:0,shell:0,lit:colour});
      const source=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,.012,12),mat);source.rotation.x=Math.PI/2;source.position.set(x,y,z);source.layers.enable(GLOW);home.add(source);
      const volMat=new THREE.SpriteMaterial({map:glowTexture(),color:colour,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false});
      const volume=new THREE.Sprite(volMat);volume.position.set(x,y-.18,z);volume.scale.set(distance*1.1,distance*.9,1);volume.layers.enable(GLOW);home.add(volume);
      const poolMat=new THREE.MeshBasicMaterial({map:glowTexture(),color:colour,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false,side:THREE.DoubleSide});
      const pool=new THREE.Mesh(new THREE.PlaneGeometry(distance*1.2,distance*1.2),poolMat);pool.rotation.x=-Math.PI/2;pool.position.set(x,(floorY===null?(y>1?.885:.115):floorY),z);home.add(pool);
      fixtures[name]={mat,volMat,poolMat,level:0};
    }
    fixture('porch',1.93,.69,1.94,0xffa34a,1.15,.02);
    fixture('hallway',2.02,.66,.82,0xffbd67,.68);
    fixture('bedroom1',.44,1.48,1.18,0xffbd67,.72);fixture('bedroom2',1.82,1.48,1.18,0xffbd67,.72);
    fixture('bedroom3',.44,1.48,.47,0xffbd67,.72);fixture('bathroom',1.82,1.48,.47,0xffd594,.62);
    fixture('livingroom',.72,.67,1.18,0xffaf5b,1.15);
    fixture('spot1',.18,.67,1.18,0xffc16c,.62);fixture('spot2',.62,.67,1.18,0xffc16c,.62);fixture('spot3',1.06,.67,1.18,0xffc16c,.62);
    const ledStrip=new THREE.Mesh(new THREE.BoxGeometry(.025,.035,.88),holo(0x176987,{base:.08,rim:.3,scan:0,shell:0,lit:0x7fe0ff}));ledStrip.position.set(X0+.018,.55,.83);ledStrip.layers.enable(GLOW);home.add(ledStrip);
    const tvScreen=new THREE.Mesh(new THREE.BoxGeometry(.035,.25,.42),holo(0x0a2940,{base:.04,rim:.2,scan:0,shell:0,lit:0x6fb8ff}));tvScreen.position.set(.70,.45,.22);tvScreen.layers.enable(GLOW);home.add(tvScreen);
    const tvGlowMat=new THREE.SpriteMaterial({map:glowTexture(),color:0x4a9ee0,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false});
    const tvGlow=new THREE.Sprite(tvGlowMat);tvGlow.position.set(.66,.45,.34);tvGlow.scale.set(.8,.6,1);home.add(tvGlow);
    const alarmBox=new THREE.Mesh(new THREE.BoxGeometry(.13,.10,.038),holo(0x3f8fb1,{base:.08,rim:.35,scan:0,shell:0,lit:0xffaa55}));alarmBox.position.set(.92,1.35,D+.035);alarmBox.layers.enable(GLOW);home.add(alarmBox);
    const alarmLed=new THREE.Mesh(new THREE.SphereGeometry(.018,8,6),new THREE.MeshBasicMaterial({color:0x3f8fb1,transparent:true,opacity:.35,blending:THREE.AdditiveBlending,depthWrite:false}));alarmLed.position.set(.92,1.35,D+.06);alarmLed.layers.enable(GLOW);home.add(alarmLed);

    // --- presence: anonymous point figures, approximate by design ---
    const FIG_N=360, figPts=[];
    for(let i=0;i<FIG_N;i++){
      const r=hash(i),u=hash(i+.5)*Math.PI*2,v=hash(i+.25);let p;
      if(r<.14){const th=Math.acos(2*v-1);p=[.045*Math.sin(th)*Math.cos(u),.43+.05*Math.cos(th),.045*Math.sin(th)*Math.sin(u)];}        // head
      else if(r<.52){p=[.07*Math.cos(u)*(.8+.2*v),.2+.17*v,.045*Math.sin(u)];}                                                          // torso
      else if(r<.76){const s=v<.5?-1:1;p=[s*.035+.018*Math.cos(u),.2*hash(i+.7),.02*Math.sin(u)];}                                     // legs
      else{const s=v<.5?-1:1,t=hash(i+.9);p=[s*(.085+.02*t)+.012*Math.cos(u),.36-.17*t,.012*Math.sin(u)];}                                // arms
      figPts.push(p);
    }
    const figures={};
    function presenceFigure(name,x,y,z){const c=pointCloud(FIG_N,0xa6ecff,.016,home);c.points.position.set(x,y,z);figures[name]={cloud:c,level:0};}
    presenceFigure('porch',1.93,.05,2.10);presenceFigure('external',1.42,.05,2.06);
    presenceFigure('livingroom',.72,.16,1.10);presenceFigure('bedroom',.44,.84,1.18);presenceFigure('upstairs',1.82,.84,.48);

    // --- energy: particles along real routes ---
    const CORE=[1.95,.32,.55];                       // where supply meets the house wiring
    const GRID=[X0-.45,.02,.25];                     // approximate service entry, beside the house
    const polyline=(pts)=>{const seg=[];let len=0;for(let i=1;i<pts.length;i++){const a=pts[i-1],b=pts[i],l=Math.hypot(b[0]-a[0],b[1]-a[1],b[2]-a[2]);seg.push({a,b,l,from:len});len+=l;}return{seg,len};};
    const at=(pl,u)=>{let d=u*pl.len;for(const s of pl.seg){if(d<=s.l||s===pl.seg[pl.seg.length-1]){const t=s.l?clamp(d/s.l,0,1):0;return[s.a[0]+(s.b[0]-s.a[0])*t,s.a[1]+(s.b[1]-s.a[1])*t,s.a[2]+(s.b[2]-s.a[2])*t];}d-=s.l;}return pl.seg[0].a;};
    const flows={
      solar:{pl:polyline([roofCentre,[.73,H+.02,D*.7],[.9,.9,.9],[1.4,.6,.7],CORE]),cloud:pointCloud(56,0x5cb4ff,.03,home),level:0,speed:0},
      grid:{pl:polyline([GRID,[X0-.05,.06,.25],[.4,.08,.35],[1.2,.14,.45],CORE]),cloud:pointCloud(56,0xffb45a,.03,home),level:0,speed:0,reverse:false},
      car:{pl:polyline([CORE,[2.3,.3,1.2],[1.52,.42,1.78],[1.2,.25,2.2],[.95,.22,2.55]]),cloud:pointCloud(40,0xffd060,.032,home),level:0,speed:0},
    };

    // --- weather, outside the house, same real thresholds as the classic ---
    const RAIN_N=240;
    const rainGeo=new THREE.BufferGeometry();rainGeo.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(RAIN_N*6),3));
    const rainMat=new THREE.LineBasicMaterial({color:0x8fd4ff,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false});
    const rain=new THREE.LineSegments(rainGeo,rainMat);rain.frustumCulled=false;rain.layers.enable(GLOW);scene.add(rain);
    const snow=pointCloud(260,0xe8f6ff,.035,scene);
    const heat=pointCloud(60,0xffb36a,.04,scene);

    // Night-light: at rest after dark the house keeps a faint warm core.
    const night={level:0};

    let doorOpen=0,carPresence=1,carStateReady=false,tvLevel=0,ledLevel=0,alarmLevel=0,focusLevel=0,cameraReady=false;
    const focusTarget=new THREE.Vector3(1.25,1.08,.95),focusCamera=new THREE.Vector3(),idleCamera=new THREE.Vector3();
    const thermalStops=[[16,0x155ab6],[18,0x9be6ff],[20,0x45bce8],[21,0xff7600],[22,0xff1800],[24,0xc90008],[26,0x700008]];
    function thermalColour(value){const t=clamp(Number(value),16,26);for(let i=1;i<thermalStops.length;i++){if(t<=thermalStops[i][0]){const a=thermalStops[i-1],b=thermalStops[i],f=(t-a[0])/(b[0]-a[0]);return new THREE.Color(a[1]).lerp(new THREE.Color(b[1]),f);}}return new THREE.Color(thermalStops[thermalStops.length-1][1]);}
    function setFixture(name,on,intensity=1){const f=fixtures[name];if(!f)return;f.level+=((on?intensity:0)-f.level)*.11;f.mat.uniforms.uLevel.value=f.level;f.volMat.opacity=f.level*.13*shared.uFade.value;f.poolMat.opacity=f.level*.18*shared.uFade.value;}
    function setThermal(name,value){const zone=roomZones[name];if(!zone)return;const valid=num(value),target=valid?thermalColour(value):new THREE.Color(0x0b5270);zone.material.color.lerp(target,.07);const opacity=(valid?.075:.035)*shared.uFade.value;zone.material.opacity+=(opacity-zone.material.opacity)*.2;}
    function setFloorThermal(floor,value,base){const valid=num(value),thermal=valid?thermalColour(value):base.clone();floor.material.color.lerp(base.clone().lerp(thermal,valid?.88:0),.075);const o=(valid?.40:.14)*shared.uFade.value;floor.material.opacity+=(o-floor.material.opacity)*.2;}
    const figScratch=new THREE.Vector3();
    // Phase advances with elapsed time, not per frame, so particle speed
    // is the same at any frame rate and captures repeat.
    function drawFlow(f,dt,active,speed){
      f.level+=((active?1:0)-f.level)*.06;
      const a=f.cloud.alpha.array,p=f.cloud.pos.array,n=f.cloud.count;
      f.phase=((f.phase||0)+speed*dt)%1;
      for(let i=0;i<n;i++){
        let u=(i/n+f.phase)%1;if(f.reverse)u=1-u;
        const q=at(f.pl,u);p[i*3]=q[0];p[i*3+1]=q[1];p[i*3+2]=q[2];
        a[i]=f.level*(.35+.65*Math.sin(Math.PI*((i/n+f.phase)%1)))*(.6+.4*hash(i));
      }
      f.cloud.pos.needsUpdate=f.cloud.alpha.needsUpdate=true;
    }

    // --- per-frame state, mirroring the classic's bindings ---
    let lastNow=null, buildStart=null, wasActive=false;
    function frame(now, fade, aspect, tuning, viewportH) {
      if(now-received>30)state={};
      const dt=lastNow===null?0:clamp(now-lastNow,0,.1);lastNow=now;
      const tune=(key,fallback)=>Number.isFinite(Number(tuning[key]))?Number(tuning[key]):fallback;
      // Build-in whenever the house (re)appears on the glass.
      const activeNow=fade>0.002;
      if(activeNow&&!wasActive)buildStart=now;
      wasActive=activeNow;
      shared.uBuild.value=buildStart===null?1:clamp((now-buildStart)/2.4,0,1);
      shared.uFade.value=fade;shared.uTime.value=now;shared.uGain.value=tune('home_brightness',1);
      // Rest scan: one slow pass up through the house every 40 s.
      const passT=now%40;shared.uPass.value=passT<3.2?-.2+passT*1.0:-10;

      const rooms=state.rooms||{},devices=state.devices||{},car_=state.car||{};
      const wattsNow=Number(state.watts_now),solarW=Number(state.solar_watts);
      const grid=num(Number(state.grid_watts))?Number(state.grid_watts):(num(wattsNow)?wattsNow:NaN);
      const solarPower=num(solarW)?solarW:(num(grid)&&grid<0?-grid:0);
      const chargerLoad=car_.charging===true||(car_.charging===undefined&&num(wattsNow)&&wattsNow>6000);
      const gen=clamp(solarPower/2800,0,1);
      solar.uniforms.uLevel.value=gen*.8;

      windows.forEach(w=>{const lit=rooms[w.room]&&rooms[w.room].light===true;const u=w.m.material.uniforms;u.uLevel.value+=((lit?1:0)-u.uLevel.value)*.1;});
      const living=rooms.livingroom||{},bedroom=rooms.bedroom||{},upstairs=rooms.upstairs||{};
      setFixture('porch',rooms.porch&&rooms.porch.light===true);setFixture('hallway',rooms.hallway&&rooms.hallway.light===true);
      setFixture('bedroom1',rooms.bedroom1&&rooms.bedroom1.light===true||bedroom.light===true);setFixture('bedroom2',rooms.bedroom2&&rooms.bedroom2.light===true||upstairs.light===true);setFixture('bedroom3',rooms.bedroom3&&rooms.bedroom3.light===true||upstairs.light===true);setFixture('bathroom',rooms.bathroom&&rooms.bathroom.light===true);
      setFixture('livingroom',living.light===true);for(const n of ['spot1','spot2','spot3'])setFixture(n,living.spotlights===true,.78);
      ledLevel+=((living.led===true?1:0)-ledLevel)*.10;ledStrip.material.uniforms.uLevel.value=ledLevel;
      tvLevel+=((devices.tv===true?1:0)-tvLevel)*.09;tvScreen.material.uniforms.uLevel.value=tvLevel*(.85+.15*Math.sin(now*3.1)*Math.sin(now*1.7));tvGlowMat.opacity=tvLevel*.35*fade;
      doorOpen+=((devices.front_door_open===true?1:0)-doorOpen)*.08;doorPivot.rotation.y=-doorOpen*.95;
      const alarm=String(devices.alarm||''),triggered=/trigger|alarm/.test(alarm),armed=/armed/.test(alarm),alarmColour=triggered?0xf0352e:(armed?0xffaa55:0x3f8fb1),alarmTarget=triggered?1:(armed?.45:0);
      alarmLevel+=(alarmTarget-alarmLevel)*.1;alarmBox.material.uniforms.uLitColor.value.setHex(alarmColour);alarmBox.material.uniforms.uLevel.value=alarmLevel*(triggered?.7+.3*Math.sin(now*6):1);alarmLed.material.color.setHex(alarmColour);alarmLed.material.opacity=(.22+alarmLevel*.7)*fade;

      const openTarget=curtainState.known?curtainState.target:1;
      const curtainDt=curtainState.lastAt===null?0:clamp(now-curtainState.lastAt,0,.12);
      curtainState.lastAt=now;
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

      chargerFace.material.uniforms.uLevel.value=chargerLoad?.8:0;chargerLed.material.color.setHex(chargerLoad?0xffb24a:0x48bddd);chargerLed.material.opacity=(chargerLoad?.7:.3)*fade;
      const carTarget=devices.car_present===false?0:1;
      if(!carStateReady){carPresence=carTarget;carStateReady=true;}else carPresence+=(carTarget-carPresence)*.018;
      car.visible=carTarget>0||carPresence>.012;
      car.position.z=.34+(1-carPresence)*1.45;
      car.scale.x=car.scale.z=.88+carPresence*.12;
      // Charging: the car's shell slowly breathes yellow.
      carPaint.uniforms.uLevel.value=chargerLoad&&carTarget>0?.25+.2*Math.sin(now*2.2):0;
      carChargeLed.material.opacity=chargerLoad&&carTarget>0?(.5+.4*Math.sin(now*2.2))*fade:0;

      const cameras=state.cameras||{},porchActive=rooms.porch&&rooms.porch.occupied===true,externalActive=rooms.external&&rooms.external.occupied===true;
      doorbellLens.material.color.setHex(porchActive?0xffa34a:0x285b72);doorbellLens.material.opacity=(porchActive?.8+.2*Math.sin(now*5):(cameras.doorbell?.5:.28))*fade;
      cameraLens.material.color.setHex(externalActive?0xffa34a:0x285b72);cameraLens.material.opacity=(externalActive?.8+.2*Math.sin(now*5.3):(cameras.external?.5:.28))*fade;

      // Presence: assemble, breathe, dissolve upward as the sensor clears.
      for(const name of Object.keys(figures)){
        const f=figures[name],active=rooms[name]&&rooms[name].occupied===true;
        f.level+=((active?1:0)-f.level)*.08;
        const c=f.cloud,p=c.pos.array,a=c.alpha.array;
        if(f.level<.01&&!active){if(f.drawn){a.fill(0);c.alpha.needsUpdate=true;f.drawn=false;}continue;}
        const scatter=1-f.level,breathe=1+.02*Math.sin(now*1.6);
        for(let i=0;i<FIG_N;i++){
          const q=figPts[i],h=hash(i*1.7);
          p[i*3]=q[0]*breathe+(h-.5)*.25*scatter;
          p[i*3+1]=q[1]*breathe+scatter*(.15+.35*h)+.004*Math.sin(now*3+i);
          p[i*3+2]=q[2]*breathe+(hash(i*2.3)-.5)*.25*scatter;
          a[i]=f.level*(.26+.3*hash(i*3.1))*(.8+.2*Math.sin(now*4+i));
        }
        c.pos.needsUpdate=c.alpha.needsUpdate=true;f.drawn=true;
      }

      // Energy: particles only for flows the data actually shows.
      const solarOn=solarPower>40, gridIn=num(grid)&&grid>40, gridOut=num(grid)&&grid<-40;
      drawFlow(flows.solar,dt,solarOn,.08+clamp(solarPower/4000,0,1)*.35);
      flows.grid.reverse=gridOut;
      // Import is restrained amber; export is generation blue, per the brief.
      flows.grid.cloud.points.material.uniforms.uColor.value.setHex(gridOut?0x5cb4ff:0xffb45a);
      drawFlow(flows.grid,dt,gridIn||gridOut,.08+clamp(Math.abs(grid||0)/4000,0,1)*.35);
      drawFlow(flows.car,dt,chargerLoad&&carTarget>0,.18);

      // Weather: the classic's real thresholds, drawn with more weight.
      const weather=state.weather||{},rainR=Number(weather.rain_mm_h),snowR=Number(weather.snow_mm_h),wind=Number(weather.wind_mph),outsideTemp=Number(weather.temperature_c),condition=String(weather.condition||'').toLowerCase();
      const heavyRain=num(rainR)&&rainR>=4, snowfall=num(snowR)&&snowR>0&&condition.includes('snow'), strongWind=num(wind)&&wind>=40, highHeat=num(outsideTemp)&&outsideTemp>=28;
      const rainStrength=heavyRain?clamp((rainR-4)/8,0,1):0, windStrength=strongWind?clamp((wind-40)/40,0,1):0;
      const slant=strongWind?.35+windStrength*.5:.08;
      rainMat.opacity=heavyRain?(.30+rainStrength*.30)*fade:0;
      if(heavyRain){
        const ra=rainGeo.attributes.position.array,len=.16+rainStrength*.1,fall=2.6+rainStrength*1.4;
        for(let i=0;i<RAIN_N;i++){
          const x=-1.2+hash(i)*4.8,z=-.8+hash(i+.3)*3.6,y=3.4-((now*fall+hash(i+.6)*3.4)%3.4);
          ra[i*6]=x+slant*(3.4-y)*.3;ra[i*6+1]=y;ra[i*6+2]=z;
          ra[i*6+3]=ra[i*6]+slant*len;ra[i*6+4]=y-len;ra[i*6+5]=z;
        }
        rainGeo.attributes.position.needsUpdate=true;
      }
      const snowField=(cloud,on,fallRate,drift,alpha,topY=3.2)=>{
        const p=cloud.pos.array,a=cloud.alpha.array;
        for(let i=0;i<cloud.count;i++){
          const y=topY-((now*fallRate+hash(i+.2)*topY)%topY);
          p[i*3]=-1.2+hash(i)*4.8+Math.sin(now*.7+i)*.05+drift*(topY-y);p[i*3+1]=y;p[i*3+2]=-.8+hash(i+.4)*3.6;
          a[i]=on?alpha*(.5+.5*hash(i+.9)):0;
        }
        cloud.pos.needsUpdate=cloud.alpha.needsUpdate=true;
      };
      if(snowfall||snow.drawn){snowField(snow,snowfall,.12,strongWind?.2:.03,.8);snow.drawn=snowfall;}
      if(highHeat||heat.drawn){snowField(heat,highHeat,-.05,.01,.35);heat.drawn=highHeat;}
      // Lightning only when real storm conditions accompany the threshold.
      const storm=/thunder|storm/.test(condition)&&(heavyRain||strongWind);
      const bolt=Math.floor(now/2.3),boltAt=now-bolt*2.3;
      shared.uFlash.value=storm&&hash(bolt)>.72&&boltAt<.16?(1-boltAt/.16):0;

      // Camera director, as the classic: eased idle orbit, event focus.
      let wanted=null;
      if(triggered)wanted=[.92,1.35,D];
      else if(porchActive)wanted=[1.93,.45,2.0];
      else if(externalActive)wanted=[1.42,.35,2.06];
      else if(now<curtainState.eventUntil)wanted=roomAnchors.livingroom;
      else if(living.occupied===true)wanted=roomAnchors.livingroom;
      else if(rooms.bedroom&&rooms.bedroom.occupied===true)wanted=roomAnchors.bedroom1;
      else if(upstairs.occupied===true)wanted=roomAnchors.bedroom2;
      focusLevel+=((wanted?1:0)-focusLevel)*.07;
      shared.uFocus.value=focusLevel;
      document.documentElement.style.setProperty('--twin-focus',focusLevel.toFixed(3));
      const pause=tune('home_orbit_pause',7),travel=tune('home_orbit_seconds',54),orbitCycle=(pause+travel)*2;
      const orbitAt=now%orbitCycle;let orbitSide;
      if(orbitAt<pause)orbitSide=-1;
      else if(orbitAt<pause+travel){const x=(orbitAt-pause)/travel;orbitSide=-Math.cos(Math.PI*x);}
      else if(orbitAt<pause+travel+pause)orbitSide=1;
      else{const x=(orbitAt-pause-travel-pause)/travel;orbitSide=Math.cos(Math.PI*x);}
      const azimuth=orbitSide*(Math.PI*tune('home_orbit_angle',45)/180),radius=tune('home_camera_radius',6.0);
      const idleTarget=new THREE.Vector3(tune('home_target_x',1.25),tune('home_target_y',1.08),tune('home_target_z',.95));
      idleCamera.set(idleTarget.x+Math.sin(azimuth)*radius,tune('home_camera_height',4.25),idleTarget.z+Math.cos(azimuth)*radius);
      if(wanted)focusTarget.lerp(new THREE.Vector3(...wanted),.11);else focusTarget.lerp(idleTarget,.055);
      focusCamera.copy(idleCamera).sub(focusTarget).normalize().multiplyScalar(4.7).add(focusTarget);focusCamera.y=Math.max(focusCamera.y,focusTarget.y+1.35);
      if(!cameraReady){camera.position.copy(idleCamera);camera.lookAt(focusTarget);cameraReady=true;}
      camera.position.lerp(idleCamera,.08).lerp(focusCamera,focusLevel);camera.lookAt(focusTarget);

      // The actor's rect is the classic's canvas box plus a margin on every
      // side. Widening the field of view by the same proportion keeps the
      // house exactly the classic's size while giving it room to fade out.
      const baseFov=tune('home_camera_fov',33)-focusLevel*6;
      const grow=aspect.growH;
      camera.fov=2*Math.atan(Math.tan(baseFov*Math.PI/360)*grow)*180/Math.PI;
      camera.aspect=aspect.value;
      camera.updateProjectionMatrix();
      // Mirror, as the classic's CSS scaleX(-1) does, by negating x.
      camera.projectionMatrix.elements[0]*=-1;
      camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
      pointScale.value=viewportH/(2*Math.tan(camera.fov*Math.PI/360));

      home.rotation.y=-.16;home.position.y=0;
    }
    // Parts that never move and share a material are submitted as one
    // mesh: the same geometry, far fewer draw calls (the Pi's CPU cost).
    // The architecture lock builds with merge:false and checks every solid.
    const before=countDraws(home);
    if(opts.merge!==false&&THREE.BufferGeometryUtils)mergeStatic(home,[steel,wallInset,roofMat,fascia,frameMat,slatMat,deviceShared,solar,edgeMat,cellMat,planMat]);
    home.userData.draws={before,after:countDraws(home)};
    return {scene,camera,home,frame};
  }

  function countDraws(root){let n=0;root.traverse(o=>{if((o.isMesh||o.isLine||o.isPoints||o.isSprite)&&o.visible)n++;});return n;}

  function mergeStatic(root,materials){
    root.updateMatrixWorld(true);
    const inv=new THREE.Matrix4().copy(root.matrixWorld).invert();
    for(const mat of materials){
      const parts=root.children.filter(o=>o.material===mat&&(o.isMesh||o.isLineSegments));
      if(parts.length<2)continue;
      const lines=!!parts[0].isLineSegments;
      if(parts.some(o=>!!o.isLineSegments!==lines))continue;
      const geoms=parts.map(o=>{
        let g=o.geometry.clone();
        g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inv,o.matrixWorld));
        for(const k of Object.keys(g.attributes))if(k!=='position'&&(lines||k!=='normal'))g.deleteAttribute(k);
        if(g.index)g=g.toNonIndexed();
        return g;
      });
      const merged=THREE.BufferGeometryUtils.mergeBufferGeometries(geoms);
      if(!merged)continue;
      const obj=lines?new THREE.LineSegments(merged,mat):new THREE.Mesh(merged,mat);
      obj.layers.mask=parts[0].layers.mask;obj.name='merged';
      parts.forEach(o=>root.remove(o));
      root.add(obj);
    }
  }

  // ------------------------------------------------------------ mounting

  // The house keeps the classic's DOM placeholder (.house), so layout
  // tuning, the panel's slide and fade, and the watt readout all behave
  // exactly as before. Each frame the actor reads the placeholder's box on
  // the plate and draws there, on the shared stage.
  function mount(el) {
    const built=build();
    const plate=document.querySelector('.mirror');
    let now=0, rect={x:0,y:0,w:1,h:1}, fade=0;
    const aspect={value:1100/680,growH:1};
    const actor={
      name:'house', rect, feather:120, scene:built.scene, camera:built.camera,
      active(){
        if(!el.isConnected)return false;
        const panel=el.closest('.panel');
        if(panel&&panel.style.visibility==='hidden')return false;
        fade=Number(getComputedStyle(el).opacity)||0;
        return fade>0.002;
      },
      update(){
        // Same layout controls as the classic, on the same placeholder.
        const tn=state._tuning||{},tv=(k,f)=>Number.isFinite(Number(tn[k]))?Number(tn[k]):f;
        el.style.setProperty('--twin-stage-scale',tv('home_stage_scale',1).toFixed(3));
        el.style.setProperty('--twin-x',tv('home_x',0).toFixed(1)+'px');
        el.style.setProperty('--twin-y',tv('home_y',0).toFixed(1)+'px');
        const box=el.getBoundingClientRect(),p=plate.getBoundingClientRect();
        const s=p.width/Stage.W||1;
        const x=(box.left-p.left)/s,y=(box.top-p.top)/s,w=box.width/s,h=box.height/s;
        rect.x=x-MARGIN;rect.y=y-MARGIN;rect.w=w+2*MARGIN;rect.h=h+2*MARGIN;
        aspect.value=rect.w/rect.h;aspect.growH=rect.h/h;
        built.frame(now,fade,aspect,(state._tuning||{}),rect.h);
      },
    };
    Stage.register(actor);
    const frame=(t)=>{now=t;};
    frame.dispose=()=>{Stage.unregister('house');};
    return frame;
  }

  // Read-only state for QA captures.
  const debug=()=>({curtain:Object.assign({},curtainState)});
  return {update,setTuning,mount,build,debug};
})();
