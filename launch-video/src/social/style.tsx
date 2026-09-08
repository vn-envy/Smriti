import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';

export const C = {ink:'#0B0F1C',paper:'#E9EDF6',white:'#FAFBFE',mute:'#64708A',amber:'#F4A43C',teal:'#52C7BE',violet:'#B794E0',rose:'#E08AA0'};
export const colors = [C.amber,C.teal,C.violet,C.rose];
const clamp = {extrapolateLeft:'clamp' as const,extrapolateRight:'clamp' as const};
export const move = (f:number,a:number,b:number,from=0,to=1) => interpolate(f,[a,b],[from,to],{...clamp,easing:Easing.bezier(.16,1,.3,1)});
export const linear = (f:number,a:number,b:number,from=0,to=1) => interpolate(f,[a,b],[from,to],clamp);
export const Base:React.FC<React.PropsWithChildren<{dark?:boolean}>>=({children,dark=false})=><AbsoluteFill style={{background:dark?C.ink:C.paper,color:dark?C.paper:C.ink,fontFamily:'Space Grotesk',overflow:'hidden'}}>
  <div style={{position:'absolute',inset:0,background:dark?'radial-gradient(ellipse at 70% 65%,#24314780,transparent 65%)':'radial-gradient(ellipse at 35% 30%,#FFFFFF,transparent 75%)'}}/>{children}
</AbsoluteFill>;
export const Enter:React.FC<React.PropsWithChildren<{at?:number;style?:React.CSSProperties}>>=({children,at=0,style})=>{
 const f=useCurrentFrame();const p=move(f,at,at+24);
 return <div style={{opacity:p,transform:`translateY(${(1-p)*56}px)`,...style}}>{children}</div>;
};
export const Eyebrow:React.FC<React.PropsWithChildren<{color?:string}>>=({children,color=C.mute})=><div style={{fontFamily:'JetBrains Mono',fontSize:27,letterSpacing:'.1em',textTransform:'uppercase',color,marginBottom:25}}>{children}</div>;
export const Title:React.FC<React.PropsWithChildren<{size?:number;style?:React.CSSProperties}>>=({children,size=148,style})=><div style={{fontSize:size,fontWeight:600,letterSpacing:'-.06em',lineHeight:1.01,...style}}>{children}</div>;
export const FourDots:React.FC<{size?:number}>=({size=16})=><div style={{display:'flex',gap:size*.55}}>{colors.map(c=><div key={c} style={{width:size,height:size,borderRadius:'50%',background:c}}/>)}</div>;
export const Card:React.FC<React.PropsWithChildren<{style?:React.CSSProperties;dark?:boolean}>>=({children,style,dark=false})=><div style={{boxSizing:'border-box',borderRadius:30,padding:36,background:dark?'#151D2C':C.white,border:`1px solid ${dark?'#344156':'#D2D8E3'}`,boxShadow:dark?'0 30px 70px #0005':'0 30px 70px #16244216',...style}}>{children}</div>;
