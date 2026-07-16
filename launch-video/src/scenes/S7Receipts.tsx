import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, F} from '../theme';
import {Kicker, Rise, Scene, TypeOn, ramp} from '../components/ui';

/**
 * S7 · Receipts (1:22–1:34)
 * Numbers we measured, not marketing copy. Then the MCP drop-in.
 */

const CHIPS: Array<{b: string; rest: string}> = [
  {b: '1', rest: ' sqlite file'},
  {b: '0', rest: ' infrastructure'},
  {b: '~1.5k', rest: ' readable lines'},
  {b: '33', rest: ' offline tests'},
  {b: '42k', rest: ' rows/sec ingest'},
  {b: 'ms', rest: ' queries at 12k memories'},
  {b: 'apache-2.0', rest: ' · everything included'},
];

const TOOLS = ['remember', 'recall', 'search', 'facts_about', 'add_fact', 'stats'];

export const S7Receipts: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <Scene background={C.ink} fadeIn={12} fadeOut={16}>
      <AbsoluteFill style={{alignItems: 'center', paddingTop: 108}}>
        <Rise at={8}>
          <Kicker>tested, not promised</Kicker>
        </Rise>

        {/* chips */}
        <div
          style={{
            display: 'flex',
            gap: 18,
            flexWrap: 'wrap',
            justifyContent: 'center',
            maxWidth: 1250,
            marginTop: 64,
          }}
        >
          {CHIPS.map((c, i) => {
            const t0 = 30 + i * 16;
            const pop = spring({frame: frame - t0, fps, config: {damping: 11, stiffness: 190, mass: 0.7}});
            return (
              <span
                key={c.rest}
                style={{
                  fontFamily: F.mono,
                  fontSize: 24,
                  color: C.paper,
                  border: `1px solid ${C.line2}`,
                  borderRadius: 999,
                  padding: '17px 32px',
                  background: 'rgba(255,255,255,.02)',
                  opacity: frame >= t0 ? 1 : 0,
                  transform: `scale(${0.6 + 0.4 * pop})`,
                  display: 'inline-block',
                }}
              >
                <b style={{color: C.amber, fontWeight: 600}}>{c.b}</b>
                {c.rest}
              </span>
            );
          })}
        </div>

        {/* MCP drop-in */}
        <Rise at={188} dur={24} style={{marginTop: 84}}>
          <h2
            style={{
              fontFamily: F.display,
              fontWeight: 600,
              fontSize: 44,
              color: C.paper,
              letterSpacing: '-0.01em',
              margin: 0,
              textAlign: 'center',
            }}
          >
            drop it into <span style={{color: C.amber}}>any agent</span>
          </h2>
        </Rise>
        <Rise at={206} dur={22} style={{marginTop: 30}}>
          <div
            style={{
              width: 880,
              background: '#0A0E1A',
              border: `1px solid ${C.line}`,
              borderRadius: 14,
              overflow: 'hidden',
              textAlign: 'left',
            }}
          >
            <div style={{display: 'flex', gap: 7, padding: '13px 16px', borderBottom: `1px solid ${C.line}`}}>
              {[0, 1, 2].map((i) => (
                <i key={i} style={{width: 11, height: 11, borderRadius: '50%', background: C.line2, display: 'block'}} />
              ))}
            </div>
            <div style={{padding: '22px 26px', fontFamily: F.mono, fontSize: 21, lineHeight: 1.9}}>
              <span style={{color: C.faint}}>$ </span>
              <TypeOn text="smriti-mcp --db memory.db" startFrame={222} cps={24} style={{color: C.paper}} />
              <div style={{color: C.faint, fontSize: 17, opacity: ramp(frame, 268, 282)}}>
                ✓ six typed tools · stdio json-rpc · offline by default
              </div>
            </div>
          </div>
        </Rise>
        <div style={{display: 'flex', gap: 12, marginTop: 26}}>
          {TOOLS.map((t, i) => {
            const t0 = 284 + i * 7;
            return (
              <span
                key={t}
                style={{
                  fontFamily: F.mono,
                  fontSize: 15.5,
                  color: C.mute,
                  border: `1px solid ${C.line}`,
                  borderRadius: 8,
                  padding: '7px 14px',
                  opacity: ramp(frame, t0, t0 + 10),
                }}
              >
                {t}
              </span>
            );
          })}
        </div>
      </AbsoluteFill>
    </Scene>
  );
};
