import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, F} from '../theme';
import {Deva, Kicker, Rise, Scene, ramp} from '../components/ui';

/**
 * S4 · The write path (0:34–0:48)
 * Nyaya's account of memory IS the pipeline:
 * anubhava (experience) → grahana (extraction) → samskara (impression).
 */

const STATIONS = [
  {
    at: 90,
    name: 'anubhava',
    deva: 'अनुभव',
    en: 'experience',
    desc: 'episodic log — append-only, embedded, FTS-indexed',
    color: C.teal,
  },
  {
    at: 150,
    name: 'grahana',
    deva: 'ग्रहण',
    en: 'extraction',
    desc: 'one LLM call per session → atomic facts',
    color: C.violet,
  },
  {
    at: 210,
    name: 'samskara',
    deva: 'संस्कार',
    en: 'impression',
    desc: 'the consolidated fact store',
    color: C.amber,
  },
] as const;

const MSGS = [
  '"I moved to Bengaluru on June 1st."',
  '"Starting the new role next week."',
  '"Remind me about the housewarming."',
];

const FACTS = [
  {s: 'user', p: 'lives_in', o: 'Bengaluru', at: 268},
  {s: 'user', p: 'moved_on', o: '2026-06-01', at: 290},
  {s: 'user', p: 'has_event', o: 'housewarming', at: 312},
];

export const S4WritePath: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <Scene background={C.ink} fadeIn={12} fadeOut={16}>
      <AbsoluteFill style={{alignItems: 'center', paddingTop: 92}}>
        <Rise at={8}>
          <Kicker>
            the write path · named by <span style={{color: C.mute}}>nyaya</span>, two millennia early
          </Kicker>
        </Rise>
        <Rise at={30} dur={26}>
          <h1
            style={{
              fontFamily: F.display,
              fontWeight: 600,
              fontSize: 66,
              letterSpacing: '-0.02em',
              color: C.paper,
              margin: '34px 0 0',
              textAlign: 'center',
              lineHeight: 1.1,
            }}
          >
            experience leaves <span style={{color: C.amber}}>impressions</span>.
          </h1>
        </Rise>
      </AbsoluteFill>

      {/* session messages sliding into the pipeline */}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
        <div style={{position: 'relative', width: 1520, height: 460, marginTop: 130}}>
          {/* messages */}
          {MSGS.map((m, i) => {
            const t0 = 58 + i * 14;
            const fly = ramp(frame, t0, t0 + 46);
            const x = interpolate(fly, [0, 1], [-40, 116]);
            const fade = fly < 0.85 ? 1 : 1 - (fly - 0.85) / 0.15;
            return (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: x,
                  top: 6 + i * 52,
                  opacity: Math.min(ramp(frame, t0 - 6, t0 + 6), fade),
                  fontFamily: F.mono,
                  fontSize: 17,
                  color: C.mute,
                  background: C.ink2,
                  border: `1px solid ${C.line}`,
                  borderRadius: 10,
                  padding: '10px 16px',
                }}
              >
                {m}
              </div>
            );
          })}

          {/* stations */}
          <div
            style={{
              position: 'absolute',
              top: 190,
              left: 0,
              right: 0,
              display: 'flex',
              justifyContent: 'center',
              gap: 84,
            }}
          >
            {STATIONS.map((st, i) => {
              const pop = spring({frame: frame - st.at, fps, config: {damping: 14, stiffness: 120}});
              return (
                <React.Fragment key={st.name}>
                  <div
                    style={{
                      width: 380,
                      background: C.ink2,
                      border: `1px solid ${C.line2}`,
                      borderTop: `3px solid ${st.color}`,
                      borderRadius: 18,
                      padding: '26px 30px',
                      opacity: frame >= st.at ? 1 : 0,
                      transform: `scale(${0.7 + 0.3 * pop}) translateY(${(1 - pop) * 24}px)`,
                    }}
                  >
                    <div style={{display: 'flex', alignItems: 'baseline', gap: 14}}>
                      <span
                        style={{
                          fontFamily: F.display,
                          fontWeight: 600,
                          fontSize: 34,
                          color: C.paper,
                        }}
                      >
                        {st.name}
                      </span>
                      <Deva color={st.color}>
                        <span style={{fontSize: 26}}>{st.deva}</span>
                      </Deva>
                    </div>
                    <div
                      style={{
                        fontFamily: F.mono,
                        fontSize: 14,
                        color: st.color,
                        letterSpacing: '.14em',
                        textTransform: 'uppercase',
                        margin: '6px 0 12px',
                      }}
                    >
                      {st.en}
                    </div>
                    <div style={{fontFamily: F.body, fontSize: 17.5, color: C.mute, lineHeight: 1.5}}>
                      {st.desc}
                    </div>
                  </div>
                  {i < 2 && (
                    <div
                      style={{
                        alignSelf: 'center',
                        fontFamily: F.mono,
                        fontSize: 40,
                        color: C.faint,
                        opacity: ramp(frame, STATIONS[i + 1].at - 10, STATIONS[i + 1].at + 6),
                        width: 0,
                        marginLeft: -52,
                        marginRight: -32,
                      }}
                    >
                      ─▸
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>

          {/* extracted facts */}
          <div
            style={{
              position: 'absolute',
              top: 428,
              left: 0,
              right: 0,
              display: 'flex',
              justifyContent: 'center',
              gap: 18,
            }}
          >
            {FACTS.map((f) => {
              const pop = spring({frame: frame - f.at, fps, config: {damping: 12, stiffness: 160}});
              return (
                <div
                  key={f.p}
                  style={{
                    opacity: frame >= f.at ? 1 : 0,
                    transform: `scale(${0.6 + 0.4 * pop})`,
                    fontFamily: F.mono,
                    fontSize: 16.5,
                    color: C.paper,
                    background: 'rgba(244,164,60,.07)',
                    border: `1px solid rgba(244,164,60,.4)`,
                    borderRadius: 999,
                    padding: '10px 20px',
                  }}
                >
                  {f.s} <span style={{color: C.faint}}>→</span>{' '}
                  <span style={{color: C.amber}}>{f.p}</span>{' '}
                  <span style={{color: C.faint}}>→</span> {f.o}
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>

      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-end'}}>
        <Rise at={352} style={{marginBottom: 92}}>
          <p style={{fontFamily: F.mono, fontSize: 19, color: C.mute, letterSpacing: '.04em', margin: 0}}>
            facts <span style={{color: C.amber}}>and</span> raw episodes stay first-class — precision, with a recall safety net
          </p>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};
