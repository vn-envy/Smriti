import {MeshGradient} from '@paper-design/shaders-react';
import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C, F, FPS} from '../theme';
import {Rise, Scene} from '../components/ui';

/**
 * S9 · End card (1:43–1:50)
 */

export const S9EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  const pulse = 0.5 + 0.5 * Math.sin(frame * 0.13);
  const shaderMs = (frame / FPS) * 1000 * 0.35;

  return (
    <Scene background={C.ink} fadeIn={14} fadeOut={26}>
      <AbsoluteFill style={{opacity: 0.42}}>
        <MeshGradient
          colors={['#0B0F1C', '#141d3a', '#1A2238', '#42301a']}
          distortion={0.55}
          swirl={0.4}
          speed={0}
          frame={shaderMs}
          style={{width: 1920, height: 1080}}
        />
      </AbsoluteFill>

      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', textAlign: 'center'}}>
        <Rise at={12} dur={24}>
          <h1 style={{margin: 0, lineHeight: 1}}>
            <span
              style={{
                fontFamily: F.display,
                fontWeight: 700,
                fontSize: 148,
                letterSpacing: '-0.02em',
                color: C.paper,
              }}
            >
              smriti
            </span>
            <span
              style={{
                fontFamily: F.deva,
                fontWeight: 500,
                fontSize: 112,
                color: C.amber,
                marginLeft: 28,
              }}
            >
              स्मृति
            </span>
          </h1>
        </Rise>
        <Rise at={40} dur={24}>
          <p
            style={{
              fontFamily: F.display,
              fontSize: 48,
              fontWeight: 500,
              color: C.mute,
              margin: '28px 0 0',
            }}
          >
            memory that knows <span style={{color: C.amber}}>when</span>
            <span
              style={{
                display: 'inline-block',
                width: 14,
                height: 14,
                borderRadius: '50%',
                background: C.amber,
                marginLeft: 10,
                boxShadow: `0 0 0 ${pulse * 14}px rgba(244,164,60,${0.35 * (1 - pulse)})`,
              }}
            />
          </p>
        </Rise>
        <Rise at={68} dur={24}>
          <p
            style={{
              fontFamily: F.mono,
              fontSize: 23,
              color: C.faint,
              marginTop: 54,
              letterSpacing: '.06em',
            }}
          >
            github.com/<span style={{color: C.mute, fontWeight: 500}}>vn-envy/Smriti</span> · apache-2.0 ·{' '}
            <span style={{color: C.mute}}>pip install -e .</span>
          </p>
        </Rise>
        <Rise at={92} dur={24}>
          <p style={{marginTop: 34, fontFamily: F.mono, fontSize: 16, color: C.faint, letterSpacing: '.14em'}}>
            <span style={{display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: '#FF9933', marginRight: 7}} />
            <span style={{display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: '#F5F5F5', marginRight: 7}} />
            <span style={{display: 'inline-block', width: 9, height: 9, borderRadius: '50%', background: '#138808', marginRight: 14}} />
            india-built · open source
          </p>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};
