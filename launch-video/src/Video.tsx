import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  continueRender,
  delayRender,
  staticFile,
} from 'remotion';
import {loadAllFonts} from './fonts';
import {C, SCENES} from './theme';
import {FilmChrome} from './components/ui';
import {S1ColdOpen} from './scenes/S1ColdOpen';
import {S2InfraTax} from './scenes/S2InfraTax';
import {S3Reveal} from './scenes/S3Reveal';
import {S4WritePath} from './scenes/S4WritePath';
import {S5Badha} from './scenes/S5Badha';
import {S6Sangama} from './scenes/S6Sangama';
import {S7Receipts} from './scenes/S7Receipts';
import {S8Honesty} from './scenes/S8Honesty';
import {S9EndCard} from './scenes/S9EndCard';

export const SmritiLaunchVideo: React.FC = () => {
  const [handle] = useState(() => delayRender('loading fonts'));
  useEffect(() => {
    loadAllFonts()
      .then(() => continueRender(handle))
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.error('font loading failed', err);
        continueRender(handle);
      });
  }, [handle]);

  return (
    <AbsoluteFill style={{background: C.ink}}>
      <Audio src={staticFile('audio/score.wav')} volume={0.9} />

      <Sequence from={SCENES.coldOpen.from} durationInFrames={SCENES.coldOpen.dur} name="S1 · cold open">
        <S1ColdOpen />
      </Sequence>
      <Sequence from={SCENES.infraTax.from} durationInFrames={SCENES.infraTax.dur} name="S2 · the tax">
        <S2InfraTax />
      </Sequence>
      <Sequence from={SCENES.reveal.from} durationInFrames={SCENES.reveal.dur} name="S3 · reveal">
        <S3Reveal />
      </Sequence>
      <Sequence from={SCENES.writePath.from} durationInFrames={SCENES.writePath.dur} name="S4 · write path">
        <S4WritePath />
      </Sequence>
      <Sequence from={SCENES.badha.from} durationInFrames={SCENES.badha.dur} name="S5 · badha">
        <S5Badha />
      </Sequence>
      <Sequence from={SCENES.sangama.from} durationInFrames={SCENES.sangama.dur} name="S6 · sangama">
        <S6Sangama />
      </Sequence>
      <Sequence from={SCENES.receipts.from} durationInFrames={SCENES.receipts.dur} name="S7 · receipts">
        <S7Receipts />
      </Sequence>
      <Sequence from={SCENES.honesty.from} durationInFrames={SCENES.honesty.dur} name="S8 · honesty">
        <S8Honesty />
      </Sequence>
      <Sequence from={SCENES.endCard.from} durationInFrames={SCENES.endCard.dur} name="S9 · end card">
        <S9EndCard />
      </Sequence>

      <FilmChrome />
    </AbsoluteFill>
  );
};
