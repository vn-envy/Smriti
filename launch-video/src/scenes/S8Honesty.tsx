import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, F} from '../theme';
import {Deva, Rise, Scene, TypeOn, ramp} from '../components/ui';

/**
 * S8 · Honesty (1:34–1:43)
 * No self-graded headline. The harness ships in the box.
 */

export const S8Honesty: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <Scene background={C.ink} fadeIn={12} fadeOut={16}>
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: '0 120px',
        }}
      >
        <h1
          style={{
            fontFamily: F.display,
            fontWeight: 600,
            fontSize: 78,
            lineHeight: 1.12,
            letterSpacing: '-0.02em',
            color: C.paper,
            margin: 0,
          }}
        >
          <Rise at={14} dur={22}>
            no leaderboard claims.
          </Rise>
          <Rise at={54} dur={24}>
            the <span style={{color: C.amber}}>benchmark harness</span> ships in the box.
          </Rise>
        </h1>

        <Rise at={116} dur={22} style={{marginTop: 56}}>
          <div
            style={{
              width: 760,
              background: '#0A0E1A',
              border: `1px solid ${C.line}`,
              borderRadius: 14,
              textAlign: 'left',
              fontFamily: F.mono,
              fontSize: 21,
              padding: '24px 28px',
              lineHeight: 2,
            }}
          >
            <span style={{color: C.faint}}>$ </span>
            <TypeOn text="bash bench/ab.sh" startFrame={130} cps={20} style={{color: C.paper}} />
            <div style={{color: C.faint, fontSize: 17, opacity: ramp(frame, 186, 200)}}>
              fixed judge · your data · your hardware → the delta, printed
            </div>
          </div>
        </Rise>

        <Rise at={216} dur={22}>
          <p
            style={{
              fontFamily: F.mono,
              fontSize: 19,
              color: C.mute,
              marginTop: 40,
              letterSpacing: '.05em',
            }}
          >
            run your own <Deva>pariksha परीक्षा</Deva> · longmemeval + locomo included
          </p>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};
