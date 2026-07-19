import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {BEAT, E, F, SCENES, bars, beats} from './etheme';
import {
  BigType, Brand, Card, Chip, CutFlash, Deva, Fragment, Kicker, Mono, Progress,
  Stamp, StatBig, Strike, Studio, TypeLine, Words,
  beatPulse, easeOut, easeSnap, ramp, useBeatSpring,
} from './eui';
import {CoreCanvas} from './ECore';

const center: React.CSSProperties = {
  justifyContent: 'center', alignItems: 'center', textAlign: 'center',
};

/* ═════════════ ACT I · 2 · PAIN — kinetic typography (4 bars) ═════════════
 * The audit meeting, in fragments. Music here is minor and lowpass-filtered;
 * the type is heavy, crowded, and slightly off-axis to feel like pressure.  */
export const SPain: React.FC = () => {
  const f = useCurrentFrame();
  const fragments = [
    {t: 'it quoted her the old price', d: beats(5), x: -430, y: -60, r: -3, c: E.rose},
    {t: 'which memory did it read?', d: beats(6.5), x: 380, y: 40, r: 2.5, c: E.violet},
    {t: 'delete her data — all of it', d: beats(8), x: -330, y: 150, r: 2, c: E.amber},
    {t: 'who approved that?', d: beats(9.5), x: 420, y: -150, r: -2, c: E.teal},
    {t: 'the log says… something', d: beats(11), x: -100, y: 250, r: -1.5, c: E.mute},
  ];
  const dateP = ramp(f, 2, 14, 0, 1, easeSnap);
  const qOut = ramp(f, beats(13), beats(14), 1, 0);
  const verdict = f >= beats(13.5);
  return (
    <Studio tint={E.paper2}>
      <Brand opacity={0.5} />
      <AbsoluteFill style={{...center}}>
        {/* the date the auditor picks — huge, cold */}
        <div style={{opacity: dateP * qOut, transform: `translateY(${-60 - (1 - dateP) * 20}px)`}}>
          <BigType size={104} color={E.faint} track="0.06em" weight={600}>MARCH 3</BigType>
        </div>
        <div style={{opacity: qOut, transform: 'translateY(-40px)'}}>
          <Words text="What did your agent know?" size={86} start={beats(2)} step={3} />
        </div>

        {fragments.map((fr) => (
          <Fragment key={fr.t} text={fr.t} delay={fr.d} x={fr.x} y={fr.y}
            rot={fr.r} accent={fr.c} size={29} />
        ))}

        {/* the answer nobody wants to give */}
        {verdict ? (
          <AbsoluteFill style={{...center, background: 'rgba(245,247,251,0.86)'}}>
            <BigType size={132} color={E.red} delay={beats(13.5)} track="-0.045em">
              WE DON’T KNOW
            </BigType>
            <div style={{marginTop: 26, opacity: ramp(f, beats(15), beats(15.5))}}>
              <Mono size={26} color={E.mute}>— every memory layer, under audit</Mono>
            </div>
          </AbsoluteFill>
        ) : null}
      </AbsoluteFill>
    </Studio>
  );
};

/* ══════════════ ACT I · 3 · COST — the three demands (2 bars) ══════════════ */
export const SCost: React.FC = () => {
  const f = useCurrentFrame();
  const demands = [
    {l: 'AUDIT', s: 'show what it knew, and when', d: beats(1), c: E.red, r: -4},
    {l: 'ERASURE', s: 'remove her — everywhere', d: beats(3), c: E.violet, r: 3},
    {l: 'RESIDENCY', s: 'and never leave our perimeter', d: beats(5), c: E.blue, r: -2},
  ];
  return (
    <Studio tint={E.paper2}>
      <Brand opacity={0.5} />
      <AbsoluteFill style={{...center}}>
        <Kicker delay={0} color={E.red}>What lands on your desk</Kicker>
        <div style={{display: 'flex', gap: 40, marginTop: 20, alignItems: 'center'}}>
          {demands.map((d) => (
            <Stamp key={d.l} label={d.l} sub={d.s} delay={d.d} color={d.c} rot={d.r} />
          ))}
        </div>
        <div style={{marginTop: 62}}>
          <Strike at={beats(7)} size={50} color={E.ink2}>
            Most memory layers answer: “trust us.”
          </Strike>
        </div>
      </AbsoluteFill>
      <CutFlash at={beats(7)} color={E.red} />
    </Studio>
  );
};

/* ═══════════ ACT I→II · 4 · THE TURN (1 bar, lands on the chord) ═══════════ */
export const SSolve: React.FC = () => {
  const f = useCurrentFrame();
  const wipe = ramp(f, 0, 16, 0, 1, easeOut);
  const line = ramp(f, 10, 30, 0, 1, easeOut);
  const sub = ramp(f, 24, 44);
  return (
    <Studio>
      {/* white wipe: the veil lifting, synced to the filter opening in the score */}
      <AbsoluteFill style={{
        background: '#fff', clipPath: `inset(0 ${(1 - wipe) * 100}% 0 0)`,
      }} />
      <AbsoluteFill style={{...center}}>
        <div style={{opacity: line}}>
          <BigType size={92} delay={8} color={E.ink}>Memory you can prove.</BigType>
        </div>
        <div style={{
          height: 4, width: line * 520, marginTop: 24, borderRadius: 99,
          background: `linear-gradient(90deg, ${E.amber}, ${E.teal}, ${E.violet})`,
        }} />
        <div style={{
          marginTop: 24, opacity: sub, display: 'flex', alignItems: 'baseline', gap: 14,
        }}>
          <span style={{
            fontFamily: F.display, fontWeight: 700, fontSize: 40, color: E.ink,
            letterSpacing: '-0.03em',
          }}>SMRITI</span>
          <Deva size={34}>स्मृति</Deva>
          <span style={{
            fontFamily: F.mono, fontSize: 17, color: E.amberDeep, background: `${E.amber}1F`,
            border: `1px solid ${E.amber}55`, borderRadius: 7, padding: '4px 11px',
            letterSpacing: '0.14em',
          }}>ENTERPRISE</span>
        </div>
      </AbsoluteFill>
    </Studio>
  );
};

/* ═══════════════════════════ 1 · OPEN (2 bars) ═══════════════════════════ */
export const SOpen: React.FC = () => {
  const f = useCurrentFrame();
  const logo = useBeatSpring(6, 11);
  const sub = ramp(f, 26, 44);
  const line = ramp(f, 34, 58, 0, 1, easeOut);
  const pulse = beatPulse(f, 0.03);
  return (
    <Studio>
      <AbsoluteFill style={center}>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: 22,
          transform: `scale(${(0.8 + logo * 0.2) * (1 + pulse)})`, opacity: logo,
        }}>
          <span style={{
            fontFamily: F.display, fontWeight: 700, fontSize: 138, color: E.ink,
            letterSpacing: '-0.05em',
          }}>SMRITI</span>
          <Deva size={104}>स्मृति</Deva>
        </div>
        <div style={{
          height: 3, width: line * 620, background: `linear-gradient(90deg, ${E.amber}, ${E.teal}, ${E.violet})`,
          borderRadius: 99, marginTop: 26,
        }} />
        <div style={{
          fontFamily: F.display, fontSize: 46, fontWeight: 600, color: E.ink2, marginTop: 30,
          opacity: sub, transform: `translateY(${(1 - sub) * 18}px)`, letterSpacing: '-0.02em',
        }}>
          Enterprise
        </div>
        <div style={{
          fontFamily: F.body, fontSize: 24, color: E.mute, marginTop: 12, opacity: sub,
        }}>
          Memory your auditors can read.
        </div>
      </AbsoluteFill>
    </Studio>
  );
};

/* ════════════════ ACT II · 5 · TRI-TEMPORAL (4 bars) ════════════════ */
const Clock: React.FC<{
  label: string; sub: string; date: string; color: string; delay: number; icon: string;
}> = ({label, sub, date, color, delay, icon}) => {
  const s = useBeatSpring(delay, 12);
  return (
    <Card delay={delay} w={430} accent={`${color}55`} style={{textAlign: 'left'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14}}>
        <div style={{
          width: 42, height: 42, borderRadius: 12, background: `${color}1A`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22,
        }}>{icon}</div>
        <div style={{fontFamily: F.display, fontSize: 26, fontWeight: 700, color: E.ink}}>
          {label}
        </div>
      </div>
      <div style={{fontFamily: F.body, fontSize: 19, color: E.mute, marginBottom: 16}}>{sub}</div>
      <div style={{
        fontFamily: F.mono, fontSize: 30, color, fontWeight: 700,
        transform: `scale(${0.9 + s * 0.1})`,
      }}>{date}</div>
    </Card>
  );
};

export const STemporal: React.FC = () => {
  const f = useCurrentFrame();
  const answer = ramp(f, beats(11), beats(11) + 18, 0, 1, easeSnap);
  return (
    <Studio>
      <Brand />
      <AbsoluteFill style={{...center, padding: '0 90px'}}>
        <Kicker delay={2}>Tri-temporal memory</Kicker>
        <Words text="Two clocks. Never one." size={72} start={6} step={3} />
        <div style={{display: 'flex', gap: 34, marginTop: 46}}>
          <Clock label="World time" sub="when it became true" date="2026-06-01"
            color={E.teal} delay={beats(4)} icon="🌍" />
          <Clock label="Knowledge time" sub="when we learned it" date="2026-07-10"
            color={E.violet} delay={beats(6)} icon="🧠" />
        </div>
        <div style={{
          marginTop: 40, opacity: answer, transform: `translateY(${(1 - answer) * 20}px)`,
          background: '#fff', border: `2px solid ${E.amber}`, borderRadius: 20,
          padding: '20px 34px', boxShadow: `0 16px 44px ${E.amber}26`,
        }}>
          <Mono size={26} color={E.ink}>
            facts_asof(<span style={{color: E.violet}}>known</span>=<span style={{color: E.amberDeep}}>"2026-03-01"</span>) → <b>Hyderabad</b>
          </Mono>
        </div>
        <div style={{
          fontFamily: F.body, fontSize: 21, color: E.mute, marginTop: 16, opacity: answer,
        }}>
          Late corrections never rewrite what you believed then.
        </div>
      </AbsoluteFill>
      <Progress index={1} total={6} />
    </Studio>
  );
};

/* ══════════════════════ 4 · 3D CORE — the drop (4 bars) ══════════════════ */
export const SCore: React.FC = () => {
  const f = useCurrentFrame();
  const dur = SCENES.core.dur;
  const p = f / dur;
  const labels = [
    {t: 'One SQLite file', d: beats(3), y: -300, x: -430, c: E.amber},
    {t: 'Zero services', d: beats(5), y: 250, x: -400, c: E.teal},
    {t: 'Runs offline', d: beats(7), y: -230, x: 420, c: E.violet},
    {t: 'Apache-2.0', d: beats(9), y: 280, x: 400, c: E.rose},
  ];
  const title = ramp(f, beats(12.5), beats(14.5), 0, 1, easeSnap);
  return (
    <Studio tint={E.paper}>
      <CoreCanvas progress={p} />
      <Brand opacity={ramp(f, 0, 10)} />
      <AbsoluteFill>
        {labels.map((l) => {
          const s = ramp(f, l.d, l.d + 14, 0, 1, easeSnap);
          const out = ramp(f, beats(12), beats(13), 1, 0);
          return (
            <div key={l.t} style={{
              position: 'absolute', left: `calc(50% + ${l.x}px)`, top: `calc(50% + ${l.y}px)`,
              transform: `translate(-50%,-50%) scale(${0.8 + s * 0.2})`, opacity: s * out,
            }}>
              <div style={{
                fontFamily: F.mono, fontSize: 24, color: E.ink, background: 'rgba(255,255,255,0.92)',
                border: `1.5px solid ${l.c}66`, borderRadius: 999, padding: '12px 24px',
                boxShadow: `0 10px 30px ${l.c}2E`, whiteSpace: 'nowrap',
              }}>
                <span style={{color: l.c, marginRight: 10}}>●</span>{l.t}
              </div>
            </div>
          );
        })}
        <div style={{
          position: 'absolute', bottom: 120, left: 0, right: 0, textAlign: 'center',
          opacity: title, transform: `translateY(${(1 - title) * 24}px)`,
        }}>
          <div style={{
            fontFamily: F.display, fontSize: 62, fontWeight: 700, color: E.ink,
            letterSpacing: '-0.035em',
          }}>The whole enterprise stack.</div>
          <div style={{fontFamily: F.body, fontSize: 26, color: E.mute, marginTop: 10}}>
            One file. Yours.
          </div>
        </div>
      </AbsoluteFill>
      <Progress index={2} total={6} />
    </Studio>
  );
};

/* ═══════════════════════ 5 · RECEIPTS (4 bars) ═══════════════════════ */
export const SReceipts: React.FC = () => {
  const f = useCurrentFrame();
  const rows = [
    {k: 'op', v: 'context', d: beats(3)},
    {k: 'store_id', v: '8056c781…', d: beats(3.7)},
    {k: 'profile', v: 'regulated', d: beats(4.4)},
    {k: 'context_digest', v: 'b920f35a…', d: beats(5.1)},
    {k: 'prev_hash', v: '4e1c88ff…', d: beats(5.8)},
  ];
  const tamperAt = beats(9);
  const verifyAt = beats(12.5);
  const tampered = f >= tamperAt && f < verifyAt;
  const verified = f >= verifyAt;
  const shakeT = tampered ? Math.sin((f - tamperAt) * 1.3) * Math.exp(-(f - tamperAt) / 14) * 9 : 0;
  return (
    <Studio>
      <Brand />
      <AbsoluteFill style={{...center, padding: '0 120px'}}>
        <Kicker delay={1} color={E.violet}>Memory-evidence receipts</Kicker>
        <Words text="Every read leaves a receipt." size={66} start={4} step={3} />

        <div style={{display: 'flex', gap: 30, marginTop: 44, alignItems: 'center'}}>
          <Card delay={beats(2.4)} w={560} accent={tampered ? E.red : verified ? E.green : E.line}
            style={{transform: `translateX(${shakeT}px)`, textAlign: 'left'}}>
            {rows.map((r) => {
              const s = ramp(f, r.d, r.d + 10);
              const bad = tampered && r.k === 'context_digest';
              return (
                <div key={r.k} style={{
                  display: 'flex', justifyContent: 'space-between', gap: 20,
                  padding: '9px 0', borderBottom: `1px solid ${E.line}`,
                  opacity: s, transform: `translateX(${(1 - s) * -14}px)`,
                }}>
                  <Mono size={20} color={E.mute}>{r.k}</Mono>
                  <Mono size={20} color={bad ? E.red : E.ink}>
                    {bad ? 'a91f00ff…' : r.v}
                  </Mono>
                </div>
              );
            })}
            <div style={{marginTop: 16, display: 'flex', alignItems: 'center', gap: 10}}>
              <div style={{
                width: 12, height: 12, borderRadius: 99,
                background: tampered ? E.red : verified ? E.green : E.faint,
              }} />
              <Mono size={19} color={tampered ? E.red : verified ? E.green : E.mute}>
                {tampered ? 'chain violation detected' : verified ? 'verified · 0 violations' : 'hash-chained'}
              </Mono>
            </div>
          </Card>

          {/* chain links */}
          <div style={{display: 'flex', flexDirection: 'column', gap: 12}}>
            {[0, 1, 2, 3].map((i) => {
              const s = ramp(f, beats(6) + i * 5, beats(6) + i * 5 + 10, 0, 1, easeSnap);
              const broken = tampered && i === 2;
              return (
                <div key={i} style={{
                  width: 74, height: 74, borderRadius: 18,
                  background: broken ? `${E.red}14` : verified ? `${E.green}14` : '#fff',
                  border: `2px solid ${broken ? E.red : verified ? E.green : E.line}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 30, opacity: s,
                  transform: `scale(${0.7 + s * 0.3}) rotate(${broken ? 8 : 0}deg)`,
                  boxShadow: '0 8px 22px rgba(20,30,60,0.08)',
                }}>{broken ? '⚠️' : verified ? '✓' : '🔗'}</div>
              );
            })}
          </div>
        </div>

        <div style={{
          marginTop: 34, opacity: ramp(f, verifyAt, verifyAt + 12),
          fontFamily: F.body, fontSize: 23, color: E.mute,
        }}>
          Tamper the log, the chain says so. Sign it with <b style={{color: E.ink}}>your</b> key.
        </div>
      </AbsoluteFill>
      <CutFlash at={tamperAt} color={E.red} />
      <Progress index={3} total={6} />
    </Studio>
  );
};

/* ════════════════════ 6 · HOLD BEATS ERASE (3 bars) ════════════════════ */
export const SHold: React.FC = () => {
  const f = useCurrentFrame();
  const eraseAt = beats(5);
  const blockAt = beats(7);
  const blocked = f >= blockAt;
  const shieldS = useBeatSpring(blockAt, 10);
  const btnPress = interpolate(f, [eraseAt - 4, eraseAt, eraseAt + 6],
    [1, 0.92, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <Studio>
      <Brand />
      <AbsoluteFill style={{...center, padding: '0 140px'}}>
        <Kicker delay={1} color={E.rose}>Lifecycle</Kicker>
        <Words text="Legal hold beats erase." size={70} start={4} step={3} />
        <div style={{display: 'flex', alignItems: 'center', gap: 46, marginTop: 52}}>
          <div style={{
            fontFamily: F.mono, fontSize: 25, color: '#fff', background: E.red,
            borderRadius: 16, padding: '20px 34px', transform: `scale(${btnPress})`,
            boxShadow: `0 14px 36px ${E.red}44`, opacity: ramp(f, beats(3), beats(4)),
          }}>erase_session("s-jan")</div>

          <div style={{
            fontSize: 54, opacity: shieldS,
            transform: `scale(${0.5 + shieldS * 0.5}) rotate(${(1 - shieldS) * -25}deg)`,
          }}>🛡️</div>

          <Card delay={blockAt + 2} w={430} accent={`${E.amber}77`} style={{textAlign: 'left'}}>
            <Mono size={21} color={E.amberDeep} style={{marginBottom: 10}}>HeldError</Mono>
            <div style={{fontFamily: F.body, fontSize: 20, color: E.ink, lineHeight: 1.5}}>
              session <b>s-jan</b> is under an active legal hold
            </div>
            <div style={{marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6}}>
              <Mono size={17} color={E.mute}>authority · legal@corp</Mono>
              <Mono size={17} color={E.mute}>reason · litigation-2026-114</Mono>
            </div>
          </Card>
        </div>
        <div style={{
          marginTop: 40, opacity: ramp(f, beats(10), beats(11)),
          fontFamily: F.body, fontSize: 23, color: E.mute,
        }}>
          Retention sweeps, holds, and erasure — <b style={{color: E.ink}}>with the residuals listed</b>.
        </div>
      </AbsoluteFill>
      <Progress index={4} total={6} />
    </Studio>
  );
};

/* ════════════════════ 7 · PACKS + FEDERATION (4 bars) ═══════════════════ */
export const SPacks: React.FC = () => {
  const f = useCurrentFrame();
  const stores = [
    {n: 'personal', c: E.amber, d: beats(6), x: -360},
    {n: 'team', c: E.teal, d: beats(7), x: 0},
    {n: 'org', c: E.violet, d: beats(8), x: 360},
  ];
  const fuseAt = beats(10);
  const fuse = ramp(f, fuseAt, fuseAt + 20, 0, 1, easeOut);
  const sealS = useBeatSpring(beats(3.5), 11);
  return (
    <Studio>
      <Brand />
      <AbsoluteFill style={{...center, padding: '0 100px'}}>
        <Kicker delay={1} color={E.teal}>Verified knowledge packs</Kicker>
        <Words text="Ship memory like a release." size={66} start={4} step={3} />

        {/* signed pack seal */}
        <div style={{
          marginTop: 34, display: 'flex', alignItems: 'center', gap: 16,
          opacity: sealS, transform: `scale(${0.85 + sealS * 0.15})`,
        }}>
          <div style={{
            background: '#fff', border: `2px solid ${E.green}`, borderRadius: 16,
            padding: '14px 26px', display: 'flex', alignItems: 'center', gap: 12,
            boxShadow: `0 12px 32px ${E.green}22`,
          }}>
            <span style={{fontSize: 24}}>📦</span>
            <Mono size={22} color={E.ink}>org-handbook.pack</Mono>
            <span style={{
              fontFamily: F.mono, fontSize: 16, color: E.green, background: `${E.green}14`,
              borderRadius: 8, padding: '4px 10px',
            }}>signed · verified</span>
          </div>
        </div>

        {/* three stores fusing */}
        <div style={{position: 'relative', width: '100%', height: 240, marginTop: 30}}>
          {stores.map((s) => {
            const sp = ramp(f, s.d, s.d + 14, 0, 1, easeSnap);
            const x = s.x * (1 - fuse * 0.72);
            return (
              <div key={s.n} style={{
                position: 'absolute', left: `calc(50% + ${x}px)`, top: 40,
                transform: `translateX(-50%) scale(${(0.8 + sp * 0.2) * (1 - fuse * 0.12)})`,
                opacity: sp,
              }}>
                <div style={{
                  width: 190, background: '#fff', border: `2px solid ${s.c}`, borderRadius: 20,
                  padding: '20px 16px', textAlign: 'center',
                  boxShadow: `0 14px 38px ${s.c}26`,
                }}>
                  <div style={{fontSize: 30, marginBottom: 8}}>{s.n === 'personal' ? '✍️' : '🔒'}</div>
                  <Mono size={20} color={E.ink}>{s.n}</Mono>
                  <div style={{
                    fontFamily: F.mono, fontSize: 14, color: s.n === 'personal' ? E.amberDeep : E.mute,
                    marginTop: 6,
                  }}>{s.n === 'personal' ? 'writable' : 'read-only'}</div>
                </div>
              </div>
            );
          })}
          {/* RRF fusion badge */}
          <div style={{
            position: 'absolute', left: '50%', top: 200, transform: 'translateX(-50%)',
            opacity: fuse,
          }}>
            <div style={{
              fontFamily: F.mono, fontSize: 21, color: '#fff',
              background: `linear-gradient(90deg, ${E.amber}, ${E.teal}, ${E.violet})`,
              borderRadius: 999, padding: '12px 30px', boxShadow: '0 12px 30px rgba(20,30,60,0.18)',
            }}>one ranking · RRF fusion · store provenance</div>
          </div>
        </div>

        <div style={{
          marginTop: 6, opacity: ramp(f, beats(13), beats(14)),
          fontFamily: F.body, fontSize: 22, color: E.mute,
        }}>
          Writes stay yours. Packs mount read-only, verified before open.
        </div>
      </AbsoluteFill>
      <Progress index={5} total={6} />
    </Studio>
  );
};

/* ═══════════════════════ 8 · SPEC SHEET (2 bars) ═══════════════════════ */
export const SStats: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <Studio>
      <Brand />
      <AbsoluteFill style={{...center}}>
        <Kicker delay={1}>Measured, not marketed</Kicker>
        <div style={{display: 'flex', gap: 82, marginTop: 30}}>
          <StatBig value={124} label="offline tests" color={E.ink} delay={beats(1.5)} />
          <StatBig value={0} label="new dependencies" color={E.teal} delay={beats(2.5)} />
          <StatBig value={1} label="SQLite file" color={E.amber} delay={beats(3.5)} />
          <StatBig value={100} suffix="%" label="Apache-2.0" color={E.violet} delay={beats(4.5)} />
        </div>
        <div style={{
          display: 'flex', gap: 14, marginTop: 52, flexWrap: 'wrap', justifyContent: 'center',
          maxWidth: 1300,
        }}>
          {['as-of queries', 'exact lineage', 'evidence receipts', 'legal holds',
            'signed packs', 'egress fails closed'].map((s, i) => (
            <Chip key={s} label={s} delay={beats(5.5) + i * 3} color={E.ink2} />
          ))}
        </div>
      </AbsoluteFill>
    </Studio>
  );
};

/* ═════════════════════════ 9 · END CARD (2 bars) ════════════════════════ */
export const SEnd: React.FC = () => {
  const f = useCurrentFrame();
  const logo = useBeatSpring(4, 11);
  const url = ramp(f, 26, 44);
  const claim = ramp(f, 40, 60);
  const pulse = beatPulse(f, 0.02);
  return (
    <Studio>
      <AbsoluteFill style={center}>
        <div style={{
          display: 'flex', alignItems: 'baseline', gap: 20, opacity: logo,
          transform: `scale(${(0.85 + logo * 0.15) * (1 + pulse)})`,
        }}>
          <span style={{
            fontFamily: F.display, fontWeight: 700, fontSize: 116, color: E.ink,
            letterSpacing: '-0.05em',
          }}>SMRITI</span>
          <Deva size={88}>स्मृति</Deva>
        </div>
        <div style={{
          fontFamily: F.display, fontSize: 38, fontWeight: 600, color: E.ink2, marginTop: 6,
          opacity: logo,
        }}>Enterprise</div>

        <div style={{
          marginTop: 34, opacity: claim, fontFamily: F.body, fontSize: 27, color: E.mute,
          maxWidth: 900, lineHeight: 1.45,
        }}>
          A memory kernel small enough to read,<br />
          and honest enough to hand your auditor.
        </div>

        <div style={{
          marginTop: 42, opacity: url, display: 'flex', gap: 16, alignItems: 'center',
        }}>
          <Mono size={26} color={E.ink}>github.com/vn-envy/Smriti</Mono>
          <span style={{color: E.faint}}>·</span>
          <Mono size={26} color={E.amberDeep}>smriti-memory.netlify.app</Mono>
        </div>
        <div style={{
          marginTop: 26, opacity: url, fontFamily: F.mono, fontSize: 18, color: E.faint,
          letterSpacing: '0.2em',
        }}>APACHE-2.0 · RUNS OFFLINE · YOUR FILE</div>
      </AbsoluteFill>
    </Studio>
  );
};
