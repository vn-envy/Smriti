import React from 'react';
import {Base,C,Enter,Eyebrow,FourDots,Title} from './style';
import {Core} from './Core';

export const Reveal:React.FC=()=><Base dark><Core/>
 <div style={{position:'absolute',left:146,top:205}}>
  <Enter><Eyebrow color={C.amber}>A focused memory core</Eyebrow></Enter>
  <Enter at={6}><Title size={210}>smriti</Title></Enter>
  <Enter at={32} style={{fontSize:64,lineHeight:1.2,marginTop:46}}>Local.<br/>Temporal.<br/>Inspectable.</Enter>
  <Enter at={70} style={{display:'flex',alignItems:'center',gap:22,marginTop:55}}><FourDots/><span style={{fontFamily:'JetBrains Mono',fontSize:29,color:'#B7C2D5'}}>One SQLite file.</span></Enter>
 </div>
</Base>;
