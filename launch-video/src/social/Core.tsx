import React from 'react';
import {ThreeCanvas} from '@remotion/three';
import {AbsoluteFill,useCurrentFrame,useVideoConfig} from 'remotion';
import {C,colors,move} from './style';

export const Core:React.FC<{quiet?:boolean}>=({quiet=false})=>{
 const f=useCurrentFrame();const {width,height}=useVideoConfig();const entry=move(f,0,40,.75,1);
 return <AbsoluteFill><ThreeCanvas width={width} height={height} camera={{position:[0,0,11],fov:42}} gl={{alpha:true,antialias:true}}>
  <ambientLight intensity={1.1}/><directionalLight position={[2,4,5]} intensity={4} color="#FFF0D4"/><pointLight position={[-4,1,3]} color={C.teal} intensity={18}/><pointLight position={[4,-2,2]} color={C.rose} intensity={15}/>
  <group scale={entry} position={[quiet?0:2.8,quiet?0:-.25,0]} rotation={[.2+Math.sin(f/100)*.1,f*.004,0]}>
   <mesh rotation={[.1,f*.002,.2]}><icosahedronGeometry args={[1.65,0]}/><meshPhysicalMaterial color="#F3D5A0" metalness={.65} roughness={.22} clearcoat={1}/></mesh>
   <mesh scale={1.017}><icosahedronGeometry args={[1.65,0]}/><meshBasicMaterial color="#FFEDD0" wireframe transparent opacity={.28}/></mesh>
   {colors.map((color,i)=><group key={color} rotation={[.6+i*.5,.25+i*.55,f*(i%2?-.002:.002)]}>
    <mesh><torusGeometry args={[2.25+i*.18,.026,8,96]}/><meshBasicMaterial color={color} transparent opacity={.85}/></mesh>
    <mesh position={[Math.cos(f*.018+i)* (2.25+i*.18),Math.sin(f*.018+i)*(2.25+i*.18),0]}><sphereGeometry args={[.075,12,12]}/><meshBasicMaterial color={color}/></mesh>
   </group>)}
  </group>
 </ThreeCanvas></AbsoluteFill>;
};
