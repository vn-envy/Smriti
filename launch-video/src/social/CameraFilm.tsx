import React,{useEffect,useState} from 'react';
import {AbsoluteFill,cancelRender,continueRender,delayRender,Easing,interpolate,staticFile,useCurrentFrame} from 'remotion';
import {Audio} from '@remotion/media';
import {linearTiming,TransitionSeries} from '@remotion/transitions';
import {wipe} from '@remotion/transitions/wipe';
import {loadAllFonts} from '../fonts';
import {Hook} from './Hook';
import {Focus} from './Focus';
import {Reveal} from './Reveal';
import {Streams} from './Streams';
import {History} from './History';
import {Results} from './Results';
import {End} from './End';

// A frame-derived virtual camera. Identical poses create deliberate reading holds.
// Framing stays inside the 1920×1080 scene; no overscan, edge exposure or random drift.
type Pose={frame:number;scale:number;x:number;y:number};
const wide=(frame:number):Pose=>({frame,scale:1,x:960,y:540});
const ease=Easing.bezier(.77,0,.175,1);
export const cameraShots:Record<string,Pose[]>={
 hook:[wide(0),wide(35),{frame:76,scale:1.12,x:940,y:550},{frame:112,scale:1.12,x:940,y:550},wide(149)],
 focus:[{frame:0,scale:1.08,x:960,y:550},wide(48),wide(100),{frame:143,scale:1.06,x:960,y:563},{frame:168,scale:1.06,x:960,y:563},wide(187)],
 reveal:[{frame:0,scale:1.14,x:935,y:540},wide(72),wide(146),{frame:194,scale:1.06,x:985,y:555},{frame:217,scale:1.06,x:985,y:555}],
 streams:[wide(0),wide(80),{frame:123,scale:1.11,x:930,y:532},{frame:188,scale:1.13,x:940,y:532},{frame:199,scale:1.13,x:940,y:532},wide(230),wide(347)],
 history:[wide(0),wide(101),{frame:158,scale:1.14,x:935,y:540},{frame:201,scale:1.14,x:935,y:540},wide(239),wide(279),{frame:325,scale:1.1,x:950,y:545},{frame:344,scale:1.1,x:950,y:545},wide(377)],
 results:[wide(0),{frame:47,scale:1.06,x:941,y:545},{frame:83,scale:1.06,x:941,y:545},wide(110),wide(377)],
 end:[{frame:0,scale:1.09,x:957,y:546},wide(82),wide(209)],
};
export const CameraRig:React.FC<React.PropsWithChildren<{shot:keyof typeof cameraShots}>>=({shot,children})=>{
 const frame=useCurrentFrame();const poses=cameraShots[shot];
 const value=(key:'scale'|'x'|'y')=>interpolate(frame,poses.map(p=>p.frame),poses.map(p=>p[key]),{easing:ease,extrapolateLeft:'clamp',extrapolateRight:'clamp'});
 const scale=value('scale');
 return <AbsoluteFill style={{overflow:'hidden'}}><AbsoluteFill style={{transformOrigin:'0 0',transform:`translate(${960-scale*value('x')}px,${540-scale*value('y')}px) scale(${scale})`}}>{children}</AbsoluteFill></AbsoluteFill>;
};

export const CameraFilm:React.FC=()=>{
 const [handle]=useState(()=>delayRender('Loading camera film fonts'));
 useEffect(()=>{loadAllFonts().then(()=>continueRender(handle)).catch(cancelRender);},[handle]);
 const transition=(direction:'from-right'|'from-left'|'from-bottom')=><TransitionSeries.Transition presentation={wipe({direction})} timing={linearTiming({durationInFrames:18,easing:ease})}/>;
 // Starts and music cues match the original. Only overlap lengths and camera differ.
 return <AbsoluteFill><Audio src={staticFile('user-media/social-mix.wav')}/><TransitionSeries>
  <TransitionSeries.Sequence durationInFrames={168} name="Camera · the update"><CameraRig shot="hook"><Hook/></CameraRig></TransitionSeries.Sequence>
  {transition('from-right')}
  <TransitionSeries.Sequence durationInFrames={198} name="Camera · the focus"><CameraRig shot="focus"><Focus/></CameraRig></TransitionSeries.Sequence>
  {transition('from-bottom')}
  <TransitionSeries.Sequence durationInFrames={228} name="Camera · Smriti"><CameraRig shot="reveal"><Reveal/></CameraRig></TransitionSeries.Sequence>
  {transition('from-right')}
  <TransitionSeries.Sequence durationInFrames={348} name="Camera · four evidence streams"><CameraRig shot="streams"><Streams/></CameraRig></TransitionSeries.Sequence>
  {transition('from-left')}
  <TransitionSeries.Sequence durationInFrames={378} name="Camera · then and now"><CameraRig shot="history"><History/></CameraRig></TransitionSeries.Sequence>
  {transition('from-right')}
  <TransitionSeries.Sequence durationInFrames={378} name="Camera · measured retrieval"><CameraRig shot="results"><Results/></CameraRig></TransitionSeries.Sequence>
  {transition('from-bottom')}
  <TransitionSeries.Sequence durationInFrames={210} name="Camera · remember what changed"><CameraRig shot="end"><End/></CameraRig></TransitionSeries.Sequence>
 </TransitionSeries></AbsoluteFill>;
};
