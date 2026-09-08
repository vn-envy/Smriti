import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Base,C,Card,Enter,Eyebrow,move,Title} from './style';

export const Focus:React.FC=()=>{
 const f=useCurrentFrame();const settle=move(f,85,115);
 return <Base>
  <Enter style={{position:'absolute',left:146,top:100}}><Eyebrow>The memory stack keeps growing.</Eyebrow><Title size={136}>More to manage.</Title></Enter>
  <div style={{position:'absolute',left:146,top:360,display:'flex',gap:28,transform:`translateY(${-settle*25}px) scale(${1-settle*.06})`,transformOrigin:'left top'}}>
   {['Search','Relationships','Personalization'].map((label,i)=><Enter at={10+i*9} key={label}><Card style={{width:524,height:350}}>
    <div style={{fontSize:44,letterSpacing:'-.04em'}}>{label}</div>
    <svg width="450" height="200" viewBox="0 0 450 200" style={{marginTop:26}}>
     {i===0?<>{[0,1,2].map(n=><g key={n}><rect x="12" y={25+n*57} width={350-n*60} height="12" rx="6" fill={n===0?C.amber:'#D8DDE7'}/><circle cx="410" cy={31+n*57} r="12" fill={n===0?C.amber:'#D8DDE7'}/></g>)}</>:i===1?<>{[[60,80],[220,20],[340,100],[180,170]].map(([x,y],n)=><g key={n}><path d={`M220 100 L${x} ${y}`} stroke={C.violet} strokeWidth="3"/><circle cx={x} cy={y} r="16" fill={C.violet}/></g>)}<circle cx="220" cy="100" r="28" fill={C.ink}/></>:<>{[0,1,2].map(n=><g key={n}><rect x="16" y={24+n*57} width="400" height="22" rx="11" fill="#E4E8EF"/><circle cx={110+n*110} cy={35+n*57} r="18" fill={C.teal}/></g>)}</>}
    </svg>
   </Card></Enter>)}
  </div>
  <Enter at={90} style={{position:'absolute',left:146,top:790,fontSize:67,letterSpacing:'-.045em'}}>Our focus: <span style={{fontWeight:600}}>memory you can inspect.</span></Enter>
 </Base>;
};
