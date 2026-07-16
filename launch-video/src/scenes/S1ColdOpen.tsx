import React, {useMemo} from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, F, mulberry32} from '../theme';
import {Kicker, Rise, Scene, TypeOn, ramp} from '../components/ui';

/**
 * S1 · Cold open (0:00–0:08)
 * Darkness. Drifting memory motes. "agents forget."
 */

const Motes: React.FC = () => {
  const frame = useCurrentFrame();
  const motes = useMemo(() => {
    const rnd = mulberry32(108);
    return Array.from({length: 90}, () => ({
      x: rnd() * 1920,
      y: rnd() * 1080,
      r: 1 + rnd() * 2.2,
      drift: 0.06 + rnd() * 0.22,
      phase: rnd() * Math.PI * 2,
      dim: 0.25 + rnd() * 0.75,
    }));
  }, []);
  return (
    <svg
      width={1920}
      height={1080}
      viewBox="0 0 1920 1080"
      style={{position: 'absolute', inset: 0}}
    >
      {motes.map((m, i) => {
        const y = ((m.y - frame * m.drift) % 1120 + 1120) % 1120 - 20;
        const tw = 0.5 + 0.5 * Math.sin(frame * 0.03 + m.phase);
        return (
          <circle
            key={i}
            cx={m.x + Math.sin(frame * 0.01 + m.phase) * 14}
            cy={y}
            r={m.r}
            fill="#8B9CC8"
            opacity={0.16 * m.dim * (0.4 + 0.6 * tw)}
          />
        );
      })}
    </svg>
  );
};

export const S1ColdOpen: React.FC = () => {
  const frame = useCurrentFrame();
  const dimAll = 1 - ramp(frame, 214, 239) * 0.35;
  return (
    <Scene background={C.ink} fadeIn={8} fadeOut={16}>
      <Motes />
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: '0 120px',
          opacity: dimAll,
        }}
      >
        <Rise at={10} style={{marginBottom: 38}}>
          <Kicker>july 2026 · an open-source release</Kicker>
        </Rise>
        <h1
          style={{
            fontFamily: F.display,
            fontWeight: 600,
            fontSize: 108,
            lineHeight: 1.06,
            letterSpacing: '-0.02em',
            color: C.paper,
            margin: 0,
          }}
        >
          <TypeOn text="agents forget." startFrame={26} cps={13} />
        </h1>
        <Rise at={128} dur={26}>
          <p
            style={{
              fontFamily: F.display,
              fontWeight: 500,
              fontSize: 42,
              color: C.mute,
              marginTop: 34,
            }}
          >
            every session starts from <span style={{color: C.rose}}>zero</span>.
          </p>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};
