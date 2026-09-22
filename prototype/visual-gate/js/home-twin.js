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
  function buildScene(el) {
    window.__homeTwinCreate=(window.__homeTwinCreate||0)+1;
    const canvas=document.createElement('canvas');canvas.className='home-twin-webgl';canvas.width=580;canvas.height=365;el.textContent='';el.appendChild(canvas);
    const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true,powerPreference:'high-performance'});
    renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.35));renderer.setSize(580,365,false);renderer.setClearColor(0x000000,0);
    renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.28;renderer.outputEncoding=THREE.sRGBEncoding;
    const scene=new THREE.Scene();
    const camera=new THREE.PerspectiveCamera(31,580/365,.1,30);camera.position.set(5.1,3.45,5.4);camera.lookAt(1.55,.9,.95);
    const home=new THREE.Group();scene.add(home);
    const steel=new THREE.MeshStandardMaterial({color:0x0b1723,metalness:.7,roughness:.35,transparent:true,opacity:.93});
    const roofMat=new THREE.MeshStandardMaterial({color:0x102b42,metalness:.72,roughness:.28,side:THREE.DoubleSide});
    const edge=new THREE.LineBasicMaterial({color:0x78d9ff,transparent:true,opacity:.72});
    const glass=new THREE.MeshPhysicalMaterial({color:0x276a93,emissive:0x10445f,emissiveIntensity:.25,metalness:.45,roughness:.12,transparent:true,opacity:.55,side:THREE.DoubleSide});
    const solar=new THREE.MeshStandardMaterial({color:0x052e70,emissive:0x0764d5,emissiveIntensity:.2,metalness:.65,roughness:.2,side:THREE.DoubleSide});
    const dark=new THREE.MeshStandardMaterial({color:0x171a20,metalness:.72,roughness:.36});
    function box(w,h,d,mat,x,y,z){const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat);m.position.set(x,y,z);home.add(m);const l=new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone());l.position.copy(m.position);home.add(l);return m;}
    box(W,H,D,steel,W/2,H/2,D/2);
    // Existing pitched roof, garage and porch proportions retained as world coordinates.
    const frontRoof=quad([0,H,D],[W,H,D],[1.96,RIDGE,D/2],[0,RIDGE,D/2],roofMat);home.add(frontRoof);
    const hipRoof=quad([W,H,0],[W,H,D],[1.96,RIDGE,D/2],[1.96,RIDGE,D/2],roofMat);home.add(hipRoof);
    [frontRoof,hipRoof].forEach(m=>home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone())));
    box(.25,.46,.19,dark,.445,2.35,.815);
    box(.77,.71,1.67,new THREE.MeshStandardMaterial({color:0x181d27,metalness:.65,roughness:.42}),2.885,.355,1.035);
    const gRoof=quad([W,.89,.20],[3.27,.71,.20],[3.27,.71,1.87],[W,.89,1.87],roofMat);home.add(gRoof);home.add(new THREE.LineSegments(new THREE.EdgesGeometry(gRoof.geometry),edge.clone()));
    box(.54,.72,.32,new THREE.MeshStandardMaterial({color:0x211d21,metalness:.45,roughness:.38}),1.93,.36,1.81);
    const pRoof=quad([1.62,.84,D],[2.24,.84,D],[2.24,.75,2.01],[1.62,.75,2.01],roofMat);home.add(pRoof);
    // Windows are actual translucent emissive planes; only real light state changes them.
    const windows=[];
    function window(w,h,x,y,z,room){const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),glass.clone());m.position.set(x,y,z);windows.push({m,room});home.add(m);const f=new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),edge.clone());f.position.copy(m.position);home.add(f);return m;}
    window(.84,.44,.60,1.24,D+.012,'bedroom');window(.64,.44,1.74,1.24,D+.013,'upstairs');window(1.02,.42,.68,.49,D+.014,'livingroom');
    const door=window(.34,.54,1.93,.36,2.013,'door');door.material.color.setHex(0x1a536e);
    // Curtains remain real-state geometry and slide, rather than changing the window material.
    const curtainMat=new THREE.MeshStandardMaterial({color:0x303a48,metalness:.25,roughness:.65,transparent:true,opacity:.88});
    const curtains=[new THREE.Mesh(new THREE.BoxGeometry(.48,.43,.025),curtainMat),new THREE.Mesh(new THREE.BoxGeometry(.48,.43,.025),curtainMat.clone())];
    curtains.forEach(m=>{m.position.set(.68,.49,D+.03);home.add(m);});
    // Individual photovoltaic panels stay flush to their original roof pitch.
    const panels=[];const roof=(x,u)=>[x,H+(RIDGE-H)*u,D-u*D/2];
    for(let r=0;r<2;r++)for(let c=0;c<4;c++){const x0=.16+c*.29,x1=x0+.26,u0=.16+r*.26,u1=u0+.24;const m=quad(roof(x0,u0),roof(x1,u0),roof(x1,u1),roof(x0,u1),solar.clone());home.add(m);panels.push(m);home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry),new THREE.LineBasicMaterial({color:0x9beeff,transparent:true,opacity:.72})));}
    // The existing car becomes a real shaded model, still deliberately dark.
    const car=new THREE.Group();home.add(car);
    const carBody=new THREE.Mesh(new THREE.BoxGeometry(1.32,.18,.49),new THREE.MeshStandardMaterial({color:0x172b40,metalness:.82,roughness:.22}));carBody.position.set(.78,.23,2.24);car.add(carBody);
    const cabin=new THREE.Mesh(new THREE.BoxGeometry(.58,.22,.43),new THREE.MeshPhysicalMaterial({color:0x183f5c,metalness:.5,roughness:.12,transparent:true,opacity:.8}));cabin.position.set(.79,.43,2.24);car.add(cabin);
    for(const x of [.35,1.2])for(const z of [2.01,2.47]){const tyre=new THREE.Mesh(new THREE.CylinderGeometry(.12,.12,.065,14),dark);tyre.rotation.x=Math.PI/2;tyre.position.set(x,.13,z);car.add(tyre);}
    const carGlow=new THREE.Sprite(new THREE.SpriteMaterial({map:glowTexture(),color:0xffbd67,transparent:true,opacity:0,depthWrite:false,blending:THREE.AdditiveBlending}));carGlow.scale.set(1.8,.75,1);carGlow.position.set(.78,.24,2.24);home.add(carGlow);
    scene.add(new THREE.HemisphereLight(0x4ba8da,0x020508,.78));
    const cyan=new THREE.PointLight(0x4ecfff,1.4,5,2);cyan.position.set(1.25,2.7,1.6);scene.add(cyan);
    const amber=new THREE.PointLight(0xffa344,.15,3,2);amber.position.set(.7,.72,2);home.add(amber);
    const particles=[],flowLines=[],sprite=glowTexture();
    const paths=[[[.72,1.94,.92],[.92,1.45,1.05],[1.2,.83,1.05]],[[4,.17,2.5],[3.1,.35,2.0],[1.2,.78,1.05]],[[1.2,.78,1.05],[1.7,.60,.68],[2.4,.42,.32]]];
    const colours=[0x48d9ff,0xffaf62,0x7ae8ff];
    for(let p=0;p<3;p++){const group=new THREE.Group();home.add(group);for(let i=0;i<16;i++){const s=new THREE.Sprite(new THREE.SpriteMaterial({map:sprite,color:colours[p],transparent:true,opacity:0,depthWrite:false,blending:THREE.AdditiveBlending}));s.scale.set(.09,.09,.09);group.add(s);}particles.push(group);const g=new THREE.BufferGeometry().setFromPoints(paths[p].map(v=>new THREE.Vector3(...v)));const m=new THREE.LineDashedMaterial({color:colours[p],transparent:true,opacity:0,dashSize:.09,gapSize:.13,depthWrite:false,blending:THREE.AdditiveBlending});const l=new THREE.Line(g,m);l.computeLineDistances();home.add(l);flowLines.push(m);}
    const scan=new THREE.Mesh(new THREE.PlaneGeometry(3.3,2.4),new THREE.MeshBasicMaterial({color:0x57d8ff,transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending}));scan.rotation.x=-Math.PI/2;scan.position.set(1.45,.1,1.2);home.add(scan);
    function pathAt(path,t){const n=path.length-1,i=Math.min(n-1,Math.floor(t*n)),f=t*n-i,a=path[i],b=path[i+1];return[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,a[2]+(b[2]-a[2])*f];}
    return {frame(now){
      if(now-received>30)state={};
      const rooms=state.rooms||{},solarWatts=Math.max(0,Number(state.solar_watts)||0),watts=Math.max(0,Number(state.watts_now)||0);
      const solarPower=clamp(solarWatts/2800,0,1), importPower=clamp(Math.max(0,watts-solarWatts)/1600,0,1), batteryPower=state.battery&&state.battery.charging===true?1:0;
      const levels=[solarPower,importPower,batteryPower];eventEnergy*=.978;
      panels.forEach((m,i)=>{m.material.emissiveIntensity=.16+solarPower*.9+Math.sin(now*1.5+i)*solarPower*.08;m.material.color.setHSL(.60,.82,.18+solarPower*.14);});
      windows.forEach(w=>{const lit=rooms[w.room]&&rooms[w.room].light===true;w.m.material.emissive.setHex(lit?0xff992e:0x10445f);w.m.material.emissiveIntensity=lit?.65+.12*Math.sin(now*1.2):.18;});
      amber.intensity=(rooms.livingroom&&rooms.livingroom.light?1.15:.12)+eventEnergy*.22;
      const living=rooms.livingroom||{};const open=num(living.curtain_position)?clamp(living.curtain_position/100,0,1):(living.curtain==='closed'?0:1);curtains[0].position.x=.68-(.24*open);curtains[1].position.x=.68+(.24*open);curtains[0].scale.x=curtains[1].scale.x=.95-open*.78;
      carGlow.material.opacity=state.car&&state.car.charging===true?.35+.15*Math.sin(now*3):0;
      for(let g=0;g<3;g++){const level=levels[g],group=particles[g];group.visible=level>.015;flowLines[g].opacity=.03+level*.43;flowLines[g].dashOffset=-now*(.3+level*.75);group.children.forEach((s,i)=>{const t=(now*(.11+level*.23)+i/group.children.length+g*.23)%1;s.position.fromArray(pathAt(paths[g],t));s.material.opacity=(.24+level*.76)*(i%3?1:.62);s.scale.setScalar((.06+level*.075)*(i%3?1:.72));});}
      const phase=now%20,on=phase>15.5&&phase<18.1;scan.material.opacity=on?.22*Math.sin((phase-15.5)/2.6*Math.PI):0;scan.position.y=.15+(on?(phase-15.5)/2.6*1.7:0);
      home.rotation.y=-.16+Math.sin(now*.10)*.025;home.position.y=Math.sin(now*.16)*.018;camera.position.x=5.1+Math.sin(now*.10)*.11;camera.position.z=5.4+Math.cos(now*.10)*.09;camera.lookAt(1.55,.9,.95);renderer.render(scene,camera);
    },dispose(){renderer.dispose();canvas.remove();}};
  }
  function render(){return '';} // no SVG fallback: the house is a WebGL scene.
  function mount(el){let fx;return now=>{if(!fx)fx=buildScene(el);if(fx)fx.frame(now);};}
  return {update,render,mount};
})();
