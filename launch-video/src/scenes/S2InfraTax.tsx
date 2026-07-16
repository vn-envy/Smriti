import React from 'react';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {C, F} from '../theme';
import {Kicker, Rise, Scene, ramp} from '../components/ui';

/**
 * S2 · The tax (0:08–0:20)
 * The "fix" stacks up: a looming tower of infrastructure. Then it implodes.
 */

const SLABS: Array<{label: string; tag: string}> = [
  {label: 'postgres + pgvector', tag: 'to run'},
  {label: 'neo4j', tag: 'to version-match'},
  {label: 'qdrant', tag: 'to keep alive'},
  {label: 'redis', tag: 'to babysit'},
  {label: 'docker compose', tag: 'to debug'},
  {label: 'a cloud account', tag: 'to trust'},
  {label: '$249/mo pro tier', tag: 'to unlock graph'},
];

const SLAB_H = 82;
const SLAB_GAP = 12;
const DROP_START = 40;
const DROP_STEP = 26;

export const S2InfraTax: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  // camera shake: decaying kick at each slab landing
  let shake = 0;
  for (let i = 0; i < SLABS.length; i++) {
    const land = DROP_START + i * DROP_STEP + 12;
    if (frame >= land) {
      const dt = frame - land;
      shake += Math.exp(-dt * 0.28) * Math.sin(dt * 1.7) * 7;
    }
  }

  // tower zoom-out as it grows
  const zoom = interpolate(frame, [DROP_START, DROP_START + 7 * DROP_STEP], [1, 0.86], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.3, 0, 0.4, 1),
  });

  // implosion 300→336, flash 326→356
  const implode = ramp(frame, 300, 336, Easing.bezier(0.7, 0, 1, 0.3));
  const towerScale = zoom * (1 - implode);
  const towerRot = implode * 14;
  const flash = interpolate(frame, [326, 338, 358], [0, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const flicker =
    frame >= 262 && frame < 292 ? (Math.floor(frame / 3) % 2 === 0 ? 1 : 0.55) : 1;

  return (
    <Scene background={C.ink} fadeIn={10} fadeOut={2}>
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-start'}}>
        <Rise at={8} style={{marginTop: 96}}>
          <Kicker>
            the usual fix is <span style={{color: C.rose}}>infrastructure</span>
          </Kicker>
        </Rise>
      </AbsoluteFill>

      {/* the tower */}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <div
          style={{
            position: 'relative',
            width: 620,
            height: SLABS.length * (SLAB_H + SLAB_GAP),
            transform: `translateX(${shake}px) scale(${towerScale}) rotate(${towerRot}deg)`,
            transformOrigin: '50% 50%',
            opacity: flicker,
            marginTop: 30,
          }}
        >
          {SLABS.map((s, i) => {
            const t0 = DROP_START + i * DROP_STEP;
            const drop = spring({
              frame: frame - t0,
              fps,
              config: {damping: 13, mass: 0.9, stiffness: 130},
            });
            const appeared = frame >= t0;
            // stack from bottom up
            const y = (SLABS.length - 1 - i) * (SLAB_H + SLAB_GAP);
            const fallY = (1 - drop) * -560;
            const heat = i / (SLABS.length - 1);
            return (
              <div
                key={s.label}
                style={{
                  position: 'absolute',
                  top: y,
                  left: 0,
                  right: 0,
                  height: SLAB_H,
                  opacity: appeared ? 1 : 0,
                  transform: `translateY(${fallY}px) rotate(${(1 - drop) * (i % 2 ? 3 : -3)}deg)`,
                  background: C.ink2,
                  border: `1px solid ${heat > 0.55 ? 'rgba(224,138,160,.45)' : C.line2}`,
                  borderRadius: 14,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0 30px',
                  boxShadow: '0 18px 40px -18px rgba(0,0,0,.7)',
                }}
              >
                <span
                  style={{
                    fontFamily: F.mono,
                    fontSize: 25,
                    fontWeight: 500,
                    color: C.paper,
                    letterSpacing: '.02em',
                  }}
                >
                  {s.label}
                </span>
                <span
                  style={{
                    fontFamily: F.mono,
                    fontSize: 15,
                    color: heat > 0.55 ? C.rose : C.faint,
                    letterSpacing: '.06em',
                  }}
                >
                  {s.tag}
                </span>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>

      {/* bottom caption */}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-end'}}>
        <Rise at={236} style={{marginBottom: 100, opacity: 1 - implode}}>
          <p
            style={{
              fontFamily: F.mono,
              fontSize: 20,
              color: C.mute,
              letterSpacing: '.05em',
              margin: 0,
            }}
          >
            a cluster to keep alive — before your agent remembers{' '}
            <span style={{color: C.rose}}>one fact</span>
          </p>
        </Rise>
      </AbsoluteFill>

      {/* implosion flash → carries the cut into S3 */}
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: '50%',
            background: `radial-gradient(circle, rgba(255,217,160,.95), rgba(244,164,60,.55) 45%, rgba(244,164,60,0) 70%)`,
            transform: `scale(${flash * 46})`,
            opacity: flash,
          }}
        />
      </AbsoluteFill>
    </Scene>
  );
};
