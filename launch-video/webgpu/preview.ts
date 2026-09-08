import * as THREE from 'three';
import WebGPURenderer from 'three/addons/renderers/webgpu/WebGPURenderer.js';
import WebGPU from 'three/addons/capabilities/WebGPU.js';

const canvas=document.querySelector<HTMLCanvasElement>('#stage')!;
const status=document.querySelector<HTMLElement>('#renderer')!;
const kicker=document.querySelector<HTMLElement>('#kicker')!;
const headline=document.querySelector<HTMLElement>('#headline')!;
const body=document.querySelector<HTMLElement>('#body')!;
const progress=document.querySelector<HTMLElement>('#progress')!;
const replay=document.querySelector<HTMLButtonElement>('#replay')!;
const renderer=new WebGPURenderer({canvas,antialias:true,alpha:true});
await renderer.init();
const backendName=((renderer as any).backend?.constructor?.name||'').toLowerCase();
const active=backendName.includes('webgpu') && WebGPU.isAvailable();
status.textContent=active?'WEBGPU · ACTIVE':'WEBGL2 · FALLBACK';
status.dataset.active=active?'true':'false';
document.documentElement.dataset.renderer=active?'webgpu':'webgl2';
const scene=new THREE.Scene(); scene.fog=new THREE.FogExp2(0x0B0F1C,.055);
const camera=new THREE.PerspectiveCamera(48,innerWidth/innerHeight,.1,100); camera.position.z=11;
const colors=[0xF4A43C,0x52C7BE,0xB794E0,0xE08AA0];
const group=new THREE.Group(); scene.add(group);
for(let ch=0;ch<4;ch++)for(let i=0;i<150;i++){const m=new THREE.Mesh(new THREE.SphereGeometry(.025+(i%5)*.007,5,5),new THREE.MeshBasicMaterial({color:colors[ch],transparent:true,opacity:.65}));(m.userData as any)={ch,p:i/150,s:.04+(i%11)*.002};group.add(m);}
const core=new THREE.Mesh(new THREE.IcosahedronGeometry(1.25,2),new THREE.MeshPhysicalMaterial({color:0xfff1d5,roughness:.08,metalness:.18,emissive:0xF4A43C,emissiveIntensity:.18}));scene.add(core);
scene.add(new THREE.AmbientLight(0xffffff,2)); const p=new THREE.PointLight(0xF4A43C,15);p.position.set(2,2,4);scene.add(p);
const beats=[
 {at:0,k:'AI remembers',h:'Until the world<br><em>changes.</em>',b:'A useful fact can become an old fact.'},
 {at:5,k:'badha · बाध',h:'Past truth dims.<br><em>New truth takes its place.</em>',b:'Superseded with time and a successor pointer. Never erased.'},
 {at:11,k:'sangama · संगम',h:'Four retrieval channels.<br><em>One memory.</em>',b:'word · meaning · relation · time'},
 {at:18.5,k:'portable by design',h:'The whole memory.<br><em>One SQLite file.</em>',b:'Local-first. Auditable. Yours to move.'},
 {at:25,k:'open source · apache-2.0',h:'smriti <em>स्मृति</em>',b:'Memory that knows when. · github.com/vn-envy/Smriti'},
];
let start=performance.now(); let previous=-1;
replay.onclick=()=>{start=performance.now();previous=-1;replay.blur();};
function resize(){renderer.setSize(innerWidth,innerHeight);renderer.setPixelRatio(Math.min(devicePixelRatio,2));camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();}resize();addEventListener('resize',resize);
renderer.setAnimationLoop(()=>{const elapsed=(performance.now()-start)/1000;const t=Math.min(30,elapsed);const idx=Math.max(0,beats.findLastIndex(x=>t>=x.at));if(idx!==previous){previous=idx;const beat=beats[idx];document.querySelector('.copy')?.classList.remove('enter');requestAnimationFrame(()=>{kicker.textContent=beat.k;headline.innerHTML=beat.h;body.textContent=beat.b;document.querySelector('.copy')?.classList.add('enter');});}progress.style.width=`${t/30*100}%`;group.children.forEach((m:any)=>{const d=m.userData;const u=(d.p+t*d.s)%1;const x=-9+u*18;const pinch=Math.max(0,1-Math.abs(x-1)/6.5);m.position.set(x,[3.3,1.15,-1.15,-3.3][d.ch]*(1-pinch*.94)+Math.sin(u*16+d.ch)*.16,Math.sin(u*9+d.ch)*.7*(1-pinch));});core.scale.setScalar(t<18.5?.01:Math.min(1,(t-18.5)/2));core.rotation.set(t*.24,t*.38,0);group.rotation.y=Math.sin(t*.1)*.12;renderer.render(scene,camera);});
