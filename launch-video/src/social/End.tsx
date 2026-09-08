import React from 'react';
import {useCurrentFrame} from 'remotion';
import {Core} from './Core';
import {Base,C,Enter,FourDots,move,Title} from './style';

export const End:React.FC=()=>{
 const f=useCurrentFrame();
 return <Base dark><div style={{position:'absolute',inset:0,opacity:.4,transform:'translateX(530px) scale(1.2)'}}><Core quiet/></div>
  <div style={{position:'absolute',left:146,top:170}}>
   <Enter><FourDots size={23}/></Enter>
   <Enter at={8} style={{marginTop:42}}><Title size={156}>Remember<br/>what changed.</Title></Enter>
   <Enter at={40} style={{display:'flex',alignItems:'baseline',gap:34,marginTop:64}}><span style={{fontSize:91,fontWeight:600,letterSpacing:'-.06em'}}>smriti</span><span style={{fontFamily:'Noto Sans Devanagari',fontSize:65,color:C.amber}}>स्मृति</span></Enter>
   <Enter at={67} style={{fontFamily:'JetBrains Mono',fontSize:35,color:'#B7C2D5',marginTop:35}}>github.com/vn-envy/Smriti</Enter>
  </div>
  <div style={{position:'absolute',inset:0,background:C.ink,opacity:move(f,194,209)}}/>
 </Base>;
};
