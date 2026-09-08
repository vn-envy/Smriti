import React, {useEffect, useMemo, useState} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {AbsoluteFill, Audio, continueRender, delayRender, Easing, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {loadAllFonts} from '../fonts';

const C={ink:'#0B0F1C',paper:'#E9EDF6',mute:'#8B94AC',line:'#26304A',amber:'#F4A43C',teal:'#52C7BE',violet:'#B794E0',rose:'#E08AA0',merged:'#FFD9A0'};
const clamp={extrapolateLeft:'clamp' as const,extrapolateRight:'clamp' as const};
const ease=Easing.bezier(.16,1,.3,1);
const seed=(n:number)=>{let a=n;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};};

const MemoryWorld:React.FC=()=>{
  const frame=useCurrentFrame();
  const {width,height}=useVideoConfig();
  const particles=useMemo(()=>{const r=seed(71);return Array.from({length:900},(_,i)=>({ch:i%4,u:r(),j:(r()-.5),z:(r()-.5)*3,s:.014+r()*.028}));},[]);
  const cols=[C.amber,C.teal,C.violet,C.rose];
  const confluence=interpolate(frame,[230,410],[0,1],{...clamp,easing:ease});
  const core=interpolate(frame,[570,680],[0,1],{...clamp,easing:ease});
  return <AbsoluteFill><ThreeCanvas width={width} height={height} camera={{position:[0,0,12],fov:46}} gl={{antialias:true,alpha:true}}>
    <fog attach="fog" args={[C.ink,8,24]}/><ambientLight intensity={.65}/><pointLight position={[1,1,4]} color={C.amber} intensity={8}/>
    <group rotation={[.08,frame*.0012,0]}>
      {particles.map((p,i)=>{const phase=(p.u+frame*p.s/30)%1;const startY=[3.6,1.25,-1.25,-3.6][p.ch];const x=-9+phase*18;const pinch=Math.max(0,1-Math.abs(x-1.1)/7)*confluence;const y=startY*(1-pinch*.94)+Math.sin(phase*12+p.j*8)*(.18+.18*(1-confluence));const zz=p.z*(1-pinch*.75);const after=x>1.1&&confluence>.5;return <mesh key={i} position={[x,y,zz]} scale={p.s*(after?1.25:1)}><sphereGeometry args={[1,5,5]}/><meshBasicMaterial color={after?C.merged:cols[p.ch]} transparent opacity={.35+(i%7)/15}/></mesh>;})}
      <group scale={.2+core*.8} rotation={[frame*.006,frame*.011,0]}>
        <mesh><icosahedronGeometry args={[1.5,2]}/><meshPhysicalMaterial color="#fff6df" roughness={.08} metalness={.15} transmission={.36} thickness={1.4} emissive={C.amber} emissiveIntensity={.16}/></mesh>
        {[2.05,2.55,3.05].map((r,i)=><mesh key={r} rotation={[Math.PI/2+i*.45,0,frame*(i%2?-.008:.006)]}><torusGeometry args={[r,.025,8,120]}/><meshBasicMaterial color={[C.amber,C.teal,C.violet][i]} transparent opacity={.72}/></mesh>)}
      </group>
    </group>
  </ThreeCanvas></AbsoluteFill>;
};

const Copy:React.FC<{from:number;to:number;kicker:string;title:React.ReactNode;body?:React.ReactNode;align?:'left'|'center'}>=({from,to,kicker,title,body,align='left'})=>{
 const f=useCurrentFrame(); const a=interpolate(f,[from,from+18,to-18,to],[0,1,1,0],{...clamp,easing:ease});
 return <AbsoluteFill style={{opacity:a,justifyContent:'center',alignItems:align==='center'?'center':'flex-start',padding:'100px 112px',textAlign:align}}>
   <div style={{fontFamily:'JetBrains Mono',fontSize:18,letterSpacing:'.19em',textTransform:'uppercase',color:C.amber,marginBottom:24}}>{kicker}</div>
   <div style={{fontFamily:'Space Grotesk',fontWeight:600,fontSize:align==='center'?112:104,lineHeight:.98,letterSpacing:'-.045em',color:C.paper,maxWidth:1200,textShadow:'0 16px 60px #0B0F1C'}}>{title}</div>
   {body&&<div style={{fontFamily:'Inter',fontSize:32,lineHeight:1.45,color:C.mute,maxWidth:860,marginTop:30}}>{body}</div>}
 </AbsoluteFill>;
};

export const LaunchTeaser30:React.FC=()=>{
 const f=useCurrentFrame();
 const [handle]=useState(()=>delayRender('loading teaser fonts'));
 useEffect(()=>{loadAllFonts().finally(()=>continueRender(handle));},[handle]);
 return <AbsoluteFill style={{background:C.ink,overflow:'hidden'}}>
   <Audio src={staticFile('audio/enterprise-score.wav')} volume={(x)=>interpolate(x,[0,18,870,899],[0,.72,.72,0],clamp)}/>
   <MemoryWorld/>
   <div style={{position:'absolute',inset:0,background:'radial-gradient(circle at 65% 50%, transparent 0 20%, rgba(11,15,28,.28) 54%, #0B0F1C 100%)'}}/>
   <Copy from={0} to={150} kicker="AI remembers" title={<>Until the world<br/><span style={{color:C.rose}}>changes.</span></>} body="A useful fact can become an old fact."/>
   <Copy from={150} to={330} kicker="badha · बाध" title={<>Past truth dims.<br/><span style={{color:C.amber}}>New truth takes its place.</span></>} body={<>Superseded with time and a successor pointer. <span style={{color:C.paper}}>Never erased.</span></>}/>
   <Copy from={330} to={555} kicker="sangama · संगम" title={<>Four retrieval channels.<br/><span style={{color:C.merged}}>One memory.</span></>} body="word · meaning · relation · time"/>
   <Copy from={555} to={750} kicker="portable by design" title={<>The whole memory.<br/><span style={{color:C.teal}}>One SQLite file.</span></>} body="Local-first. Auditable. Yours to move."/>
   <Copy from={750} to={900} kicker="open source · apache-2.0" align="center" title={<>smriti <span style={{color:C.amber}}>स्मृति</span></>} body={<><span style={{color:C.paper}}>Memory that knows when.</span><br/><span style={{fontFamily:'JetBrains Mono',fontSize:22}}>github.com/vn-envy/Smriti</span></>}/>
   <div style={{position:'absolute',left:112,right:112,bottom:64,height:1,background:C.line}}><div style={{height:2,width:`${f/9}%`,background:`linear-gradient(90deg,${C.amber},${C.teal},${C.violet},${C.rose})`}}/></div>
 </AbsoluteFill>;
};
