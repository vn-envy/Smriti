import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Base,C,Card,colors,Enter,Eyebrow,FourDots,linear,move,Title} from './style';

const names=['Words','Meaning','Relations','Time'];
const native=['shabda','artha','sambandha','kala'];
export const Streams:React.FC=()=>{
 const f=useCurrentFrame();const converge=move(f,120,190);
 return <Base dark>
  <Enter style={{position:'absolute',left:146,top:92}}><Eyebrow color={C.amber}>संगम · sangama</Eyebrow><Title size={120}>Four paths to the evidence.</Title></Enter>
  <svg width="1920" height="1080" viewBox="0 0 1920 1080" style={{position:'absolute',inset:0}}>
   <defs>{colors.map((c,i)=><linearGradient id={`stream-${i}`} key={c}><stop stopColor={c}/><stop offset="1" stopColor={C.paper}/></linearGradient>)}</defs>
   {colors.map((color,i)=>{
    const y=380+i*145;const path=`M 560 ${y} C 850 ${y}, 965 ${y+(600-y)*converge}, 1250 600`;
    const p=move(f,14+i*16,54+i*16);
    return <g key={color} opacity={p}>
     <path d={path} fill="none" stroke={color} strokeWidth="16" opacity=".08"/>
     <path d={path} pathLength="1" fill="none" stroke={`url(#stream-${i})`} strokeWidth="3" strokeDasharray="1" strokeDashoffset={1-p}/>
     {[0,1,2,3].map(j=>{const t=(linear(f,0,330)*2+j*.25+i*.06)%1;const x=(1-t)**3*560+3*(1-t)**2*t*850+3*(1-t)*t*t*965+t**3*1250;const yy=(1-t)**3*y+3*(1-t)**2*t*y+3*(1-t)*t*t*(y+(600-y)*converge)+t**3*600;return <circle key={j} cx={x} cy={yy} r={5+j*.8} fill={color}/>;})}
    </g>;
   })}
  </svg>
  {names.map((n,i)=><Enter key={n} at={14+i*16} style={{position:'absolute',left:146,top:330+i*145,display:'flex',gap:25,alignItems:'center'}}>
   <div style={{height:64,width:6,borderRadius:6,background:colors[i]}}/><div><div style={{fontSize:53,letterSpacing:'-.04em'}}>{n}</div><div style={{fontFamily:'JetBrains Mono',fontSize:26,color:colors[i],marginTop:3}}>{native[i]}</div></div>
  </Enter>)}
  <Enter at={135} style={{position:'absolute',left:1245,top:442}}><Card dark style={{width:510,height:318,borderColor:'#556477'}}>
   <FourDots/><div style={{fontSize:48,marginTop:35,lineHeight:1.08}}>One returned<br/>context.</div><div style={{fontSize:27,color:'#B7C2D5',marginTop:25}}>Evidence, with its sources.</div>
  </Card></Enter>
  <Enter at={200} style={{position:'absolute',left:146,bottom:83,fontSize:28,color:'#A9B4C9'}}>Words · vectors · entities · dates</Enter>
 </Base>;
};
