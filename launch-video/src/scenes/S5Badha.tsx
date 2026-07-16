import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {C, F} from '../theme';
import {Deva, Rise, Scene, TypeOn, ramp} from '../components/ui';

/**
 * S5 · Badha (0:48–1:04) — the soul of the product.
 * A fact changes. The old one is superseded — never deleted.
 * One store answers both "now" and "then".
 */

const SUPERSEDE_AT = 130; // local frame where the new fact lands

const FactRow: React.FC<{
  text: string;
  active: boolean;
  visible: number; // opacity
  badge: string;
  y?: number;
}> = ({text, active, visible, badge}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      fontFamily: F.body,
      fontSize: 31,
      fontWeight: 500,
      color: active ? '#FFFFFF' : C.faint,
      marginBottom: 14,
      opacity: visible,
      transition: 'none',
    }}
  >
    <span
      style={{
        width: 13,
        height: 13,
        borderRadius: '50%',
        background: active ? C.amber : C.slate,
        boxShadow: active ? `0 0 16px ${C.amber}` : 'none',
        marginRight: 21,
        flex: 'none',
      }}
    />
    {text}
    <span
      style={{
        fontFamily: F.mono,
        fontSize: 14.5,
        letterSpacing: '.08em',
        marginLeft: 22,
        padding: '6px 14px',
        borderRadius: 8,
        background: active ? C.amber : 'transparent',
        border: active ? '1px solid transparent' : `1px solid ${C.line2}`,
        color: active ? C.ink : C.faint,
        fontWeight: active ? 700 : 400,
        whiteSpace: 'nowrap',
      }}
    >
      {badge}
    </span>
  </div>
);

const WindowBar: React.FC<{
  from: number; // 0..1 left
  to: number; // 0..1 right edge position
  active: boolean;
  opacity: number;
  draw: number; // 0..1 draw-in progress
}> = ({from, to, active, opacity, draw}) => (
  <div
    style={{
      height: 9,
      borderRadius: 5,
      background: C.ink,
      border: `1px solid ${C.line}`,
      margin: '4px 0 28px 34px',
      position: 'relative',
      overflow: 'hidden',
      opacity,
    }}
  >
    <div
      style={{
        position: 'absolute',
        top: 0,
        bottom: 0,
        left: `${from * 100}%`,
        width: `${Math.max(0, (to - from) * 100 * draw)}%`,
        borderRadius: 4,
        background: active
          ? `linear-gradient(90deg, ${C.amber}, rgba(244,164,60,.45))`
          : `linear-gradient(90deg, ${C.slate}, rgba(74,85,112,.4))`,
      }}
    />
  </div>
);

export const S5Badha: React.FC = () => {
  const frame = useCurrentFrame();
  const superseded = frame >= SUPERSEDE_AT;

  // fact A's validity window shrinks from full to first-half when superseded
  const shrink = ramp(frame, SUPERSEDE_AT, SUPERSEDE_AT + 30);
  const aTo = interpolate(shrink, [0, 1], [0.97, 0.5]);

  return (
    <Scene background={C.ink} fadeIn={12} fadeOut={16}>
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <Rise at={12} dur={24}>
          <div
            style={{
              width: 1080,
              background: C.ink2,
              border: `1px solid ${C.line}`,
              borderRadius: 22,
              padding: '48px 56px',
              textAlign: 'left',
              boxShadow: '0 40px 90px -40px rgba(0,0,0,.8)',
            }}
          >
            <p style={{fontFamily: F.mono, fontSize: 20, color: C.mute, margin: '0 0 40px'}}>
              <span style={{color: C.faint}}>query · </span>
              <TypeOn
                text={'mem.context("where does the user live?")'}
                startFrame={26}
                cps={26}
                caret={false}
                style={{color: C.paper}}
              />
            </p>

            <FactRow
              text="user lives in Hyderabad"
              active={!superseded}
              visible={ramp(frame, 56, 70)}
              badge={superseded ? 'SUPERSEDED · 2026-06-01' : 'CURRENT'}
            />
            <WindowBar
              from={0.03}
              to={aTo}
              active={!superseded}
              opacity={ramp(frame, 62, 76)}
              draw={ramp(frame, 62, 92)}
            />

            <FactRow
              text="user lives in Bengaluru"
              active={superseded}
              visible={ramp(frame, SUPERSEDE_AT, SUPERSEDE_AT + 16)}
              badge="CURRENT"
            />
            <WindowBar
              from={0.5}
              to={0.97}
              active={superseded}
              opacity={ramp(frame, SUPERSEDE_AT + 4, SUPERSEDE_AT + 18)}
              draw={ramp(frame, SUPERSEDE_AT + 4, SUPERSEDE_AT + 40)}
            />

            {/* the payoff */}
            <div
              style={{
                fontFamily: F.mono,
                fontSize: 22,
                color: C.mute,
                marginTop: 36,
                borderTop: `1px solid ${C.line}`,
                paddingTop: 30,
                lineHeight: 2.15,
                opacity: ramp(frame, 236, 254),
              }}
            >
              <span style={{opacity: ramp(frame, 240, 256)}}>
                <span style={{color: C.paper}}>"where now?"</span>{' '}
                <span style={{color: C.faint}}>→</span>{' '}
                <b style={{color: C.amber, fontWeight: 500}}>Bengaluru</b>
              </span>
              <br />
              <span style={{opacity: ramp(frame, 292, 308)}}>
                <span style={{color: C.paper}}>"before June?"</span>{' '}
                <span style={{color: C.faint}}>→</span>{' '}
                <b style={{color: C.amber, fontWeight: 500}}>Hyderabad</b>
                <span style={{color: C.faint}}> · one store, both answers</span>
              </span>
            </div>
          </div>
        </Rise>

        <Rise at={190} dur={24}>
          <p
            style={{
              fontFamily: F.mono,
              fontSize: 20,
              color: C.mute,
              marginTop: 38,
              letterSpacing: '.04em',
            }}
          >
            <Deva>badha बाध</Deva> — superseded, <span style={{color: C.paper}}>never deleted</span>
          </p>
        </Rise>

        <Rise at={392} dur={26}>
          <p
            style={{
              fontFamily: F.display,
              fontWeight: 500,
              fontSize: 30,
              color: C.mute,
              marginTop: 26,
            }}
          >
            correction is an <span style={{color: C.amber}}>event in time</span> — not an overwrite.
          </p>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};
