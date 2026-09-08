import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Base,C,Card,Enter,Eyebrow,FourDots,move,Title} from './style';

export const Hook:React.FC=()=>{
 const f=useCurrentFrame();const update=move(f,47,69);const turn=move(f,84,108);
 return <Base>
  <div style={{position:'absolute',left:146,top:140,width:1000}}>
   <Enter><Eyebrow>Agents remember conversations.</Eyebrow></Enter>
   <Enter at={5}><Title>Your agent<br/>remembers.</Title></Enter>
   <Enter at={73} style={{marginTop:40,fontSize:62,lineHeight:1.12,maxWidth:950}}>Does it know<br/><span style={{color:'#A05014'}}>what changed?</span></Enter>
  </div>
  <div style={{position:'absolute',left:1120,top:220,width:620,height:650,perspective:1300,transform:`translateX(${move(f,0,28,180,0)}px) rotate(-5deg)`}}>
   {[3,2,1].map(i=><Card key={i} style={{position:'absolute',inset:0,height:410,transform:`translate(${i*15}px,${i*27}px) rotate(${i*3}deg)`,opacity:.7-i*.12}}/>) }
   <Card style={{position:'absolute',width:610,height:390,transform:`translateY(${-update*55}px) rotateX(${turn*-8}deg)`,background:'#FFF6E7'}}>
    <FourDots/><div style={{fontSize:25,color:C.mute,marginTop:50}}>JAN 10 · PROJECT CEDAR</div><div style={{fontSize:54,marginTop:22,lineHeight:1.1}}>Leila uses Sketch.</div>
   </Card>
   <Card style={{position:'absolute',top:260,width:610,opacity:update,transform:`translateY(${(1-update)*170}px) rotate(7deg)`,borderColor:C.teal}}>
    <div style={{fontSize:25,color:C.mute}}>MAR 10 · PROJECT CEDAR</div><div style={{fontSize:48,marginTop:22,lineHeight:1.15}}>Leila switched<br/>to Figma.</div><div style={{height:5,background:C.teal,width:`${update*100}%`,marginTop:30,borderRadius:8}}/>
   </Card>
  </div>
 </Base>;
};
