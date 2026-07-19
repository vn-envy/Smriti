import React from 'react';
import {AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {E, SCENES, TOTAL_FRAMES} from './etheme';
import {CutFlash} from './eui';
import {
  SCore, SCost, SEnd, SHold, SOpen, SPacks, SPain, SReceipts, SSolve, SStats,
  STemporal,
} from './EScenes';

const ORDER = [
  {key: 'open', C: SOpen},
  {key: 'pain', C: SPain},
  {key: 'cost', C: SCost},
  {key: 'solve', C: SSolve},
  {key: 'temporal', C: STemporal},
  {key: 'core', C: SCore},
  {key: 'receipts', C: SReceipts},
  {key: 'hold', C: SHold},
  {key: 'packs', C: SPacks},
  {key: 'stats', C: SStats},
  {key: 'end', C: SEnd},
] as const;

/**
 * SMRITI Enterprise — 74.7s product film.
 *
 * Bright studio palette, Apple-keynote pacing, everything cut to a 90 BPM
 * grid (20 frames = 1 beat, 80 = 1 bar) so the motion lands with the score
 * in scripts/make-enterprise-audio.py. Three.js hero shot at the drop.
 */
export const SmritiEnterpriseVideo: React.FC = () => {
  const frame = useCurrentFrame();
  // gentle global fade in/out
  const fade = interpolate(
    frame,
    [0, 8, TOTAL_FRAMES - 24, TOTAL_FRAMES - 1],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  return (
    <AbsoluteFill style={{background: E.paper, opacity: fade}}>
      <Audio src={staticFile('audio/enterprise-score.wav')} />
      {ORDER.map(({key, C}) => {
        const s = SCENES[key];
        return (
          <Sequence key={key} from={s.from} durationInFrames={s.dur} name={key}>
            <C />
          </Sequence>
        );
      })}
      {/* white flash on every scene boundary — the "beat cut" */}
      {ORDER.slice(1).map(({key}) => (
        <CutFlash key={`f-${key}`} at={SCENES[key].from} />
      ))}
    </AbsoluteFill>
  );
};
