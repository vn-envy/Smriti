import React,{useEffect,useState} from 'react';
import {AbsoluteFill,cancelRender,continueRender,delayRender,staticFile} from 'remotion';
import {Audio} from '@remotion/media';
import {linearTiming,TransitionSeries} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {loadAllFonts} from '../fonts';
import {Hook} from './Hook';
import {Focus} from './Focus';
import {Reveal} from './Reveal';
import {Streams} from './Streams';
import {History} from './History';
import {Results} from './Results';
import {End} from './End';

export const SocialFilm:React.FC=()=>{
 const [handle]=useState(()=>delayRender('Loading social film fonts'));
 useEffect(()=>{loadAllFonts().then(()=>continueRender(handle)).catch(cancelRender);},[handle]);
 return <AbsoluteFill>
  <Audio src={staticFile('user-media/social-mix.wav')}/>
  <TransitionSeries>
   <TransitionSeries.Sequence durationInFrames={158} name="The update"><Hook/></TransitionSeries.Sequence>
   <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:8})}/>
   <TransitionSeries.Sequence durationInFrames={188} name="The focus"><Focus/></TransitionSeries.Sequence>
   <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:8})}/>
   <TransitionSeries.Sequence durationInFrames={218} name="Smriti"><Reveal/></TransitionSeries.Sequence>
   <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:8})}/>
   <TransitionSeries.Sequence durationInFrames={338} name="Four evidence streams"><Streams/></TransitionSeries.Sequence>
   <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:8})}/>
   <TransitionSeries.Sequence durationInFrames={368} name="Then and now"><History/></TransitionSeries.Sequence>
   <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:8})}/>
   <TransitionSeries.Sequence durationInFrames={368} name="Measured retrieval"><Results/></TransitionSeries.Sequence>
   <TransitionSeries.Transition presentation={fade()} timing={linearTiming({durationInFrames:8})}/>
   <TransitionSeries.Sequence durationInFrames={210} name="Remember what changed"><End/></TransitionSeries.Sequence>
  </TransitionSeries>
 </AbsoluteFill>;
};
