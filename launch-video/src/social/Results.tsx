import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Base,C,Enter,Eyebrow,move,Title} from './style';

export const Results:React.FC=()=>{
 const f=useCurrentFrame();const chart=move(f,110,140);const hero=1-chart;
 const labels=['Smriti','GBrain semantic','Mem0 OSS'];const values=[20.474,66.268,381.298];
 return <Base>
  <Enter style={{position:'absolute',left:146,top:100}}><Eyebrow>Measured on a local synthetic corpus</Eyebrow><Title size={126}>36,500 records.</Title></Enter>
  <div style={{position:'absolute',left:146,top:360,opacity:hero,transform:`translateY(${-chart*70}px)`}}>
   <span style={{fontSize:250,fontWeight:600,letterSpacing:'-.085em'}}>20.5</span><span style={{fontSize:90,marginLeft:22}}>ms</span>
   <div style={{fontSize:58,color:C.mute,marginTop:10}}>median warm retrieval</div>
  </div>
  <div style={{position:'absolute',left:146,top:352,width:1620,opacity:chart,transform:`translateY(${(1-chart)*70}px)`}}>
   {values.map((v,i)=><div key={v} style={{display:'flex',alignItems:'center',height:139}}>
    <div style={{width:440,fontSize:44,fontWeight:i===0?600:500,flexShrink:0}}>{labels[i]}</div>
    <div style={{width:1000,height:56,position:'relative',borderLeft:'2px solid #ABB5C8'}}>
     <div style={{height:'100%',width:1000*(v/400)*move(f,120+i*8,155+i*8),background:i===0?C.teal:i===1?C.violet:'#A9B3C6',borderRadius:'0 12px 12px 0'}}/>
     <div style={{position:'absolute',top:7,left:1000*(v/400)+22,fontFamily:'JetBrains Mono',fontSize:33,whiteSpace:'nowrap'}}>{v.toFixed(1)}</div>
    </div>
   </div>)}
   <div style={{marginLeft:440,display:'flex',justifyContent:'space-between',width:1000,fontFamily:'JetBrains Mono',fontSize:25,color:C.mute}}><span>0</span><span>200</span><span>400 ms</span></div>
  </div>
  <Enter at={15} style={{position:'absolute',left:146,top:850,fontSize:34,color:C.mute,lineHeight:1.42}}>Local synthetic test · 20 warm queries · Apple M5<br/>Same nomic model · pinned configs · Mem0 OSS infer=False / Qdrant<br/>Retrieval latency, not answer speed. Methodology in the repo.</Enter>
 </Base>;
};
