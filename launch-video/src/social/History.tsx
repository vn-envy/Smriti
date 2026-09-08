import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Base,C,Card,Enter,Eyebrow,linear,move,Title} from './style';

export const History:React.FC=()=>{
 const f=useCurrentFrame();
 const cursor=f<210?move(f,144,164):f<290?move(f,240,260,1,0):move(f,302,322);
 const current=cursor>.5;const showUpdate=move(f,100,127);
 return <Base>
  <Enter style={{position:'absolute',left:146,top:116}}><Eyebrow>Verified local example · project:Cedar</Eyebrow><Title size={120}>Then. Now.<br/>Both on record.</Title></Enter>
  <Enter at={45} style={{position:'absolute',left:146,top:508,fontSize:56,lineHeight:1.18,color:C.mute}}>A change in tools.<br/><span style={{color:C.ink}}>A history you can query.</span></Enter>
  <div style={{position:'absolute',left:1070,top:250,width:690,height:370,perspective:1300}}>
   <Card style={{position:'absolute',inset:0,opacity:1-cursor*.65,transform:`translate(${-cursor*35}px,${-cursor*55}px) rotate(${-cursor*6}deg)`,background:'#FFF6E7',height:325}}>
    <div style={{display:'flex',justifyContent:'space-between',fontSize:25,color:C.mute}}><span>LEILA</span><span>JAN 10, 2025</span></div><div style={{fontSize:88,marginTop:28,letterSpacing:'-.055em'}}>Sketch</div><div style={{fontSize:28,marginTop:30}}>Valid until Mar 10 · history retained</div>
   </Card>
   <Card style={{position:'absolute',inset:0,height:325,opacity:showUpdate*cursor,transform:`translateY(${(1-cursor)*80}px)`,borderColor:C.teal}}>
    <div style={{display:'flex',justifyContent:'space-between',fontSize:25,color:C.mute}}><span>LEILA</span><span>MAR 10, 2025</span></div><div style={{fontSize:88,marginTop:28,letterSpacing:'-.055em'}}>Figma</div><div style={{fontSize:28,marginTop:30}}>Active from Mar 10 · project:Cedar</div>
   </Card>
  </div>
  <div style={{position:'absolute',left:200,top:808,width:1500}}>
   <div style={{height:8,background:'#D0D7E3',borderRadius:8}}/><div style={{position:'absolute',left:0,top:0,width:650,height:8,background:C.amber,borderRadius:8}}/><div style={{position:'absolute',left:650,top:0,width:850*showUpdate,height:8,background:C.teal,borderRadius:8}}/>
   <div style={{position:'absolute',left:170+cursor*900,top:-21,width:48,height:48,borderRadius:'50%',background:C.ink,border:'7px solid white',boxShadow:'0 8px 24px #0B0F1C30'}}/>
   <div style={{position:'absolute',left:Math.min(1070,170+cursor*900)-70,top:-87,fontFamily:'JetBrains Mono',fontSize:28}}>{current?'NOW':'AS OF JAN 20'}</div>
   <div style={{display:'flex',justifyContent:'space-between',marginTop:30,fontSize:28,color:C.mute}}><span>Jan 10 · Sketch</span><span>Mar 10 · switched to Figma</span><span>History stays.</span></div>
  </div>
 </Base>;
};
