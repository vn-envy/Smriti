import {ThreeCanvas} from '@remotion/three';
import {useThree} from '@react-three/fiber';
import React, {useLayoutEffect, useMemo} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import * as THREE from 'three';
import {C, F, FPS, mulberry32} from '../theme';
import {Deva, Kicker, Rise, Scene, ramp} from '../components/ui';

/**
 * S6 · Sangama (1:04–1:22) — the hero shot.
 * Four retrieval rivers braid through space and meet in one confluence.
 * Ported from smriti-landing.html, made deterministic (pure function of frame).
 */

const MERGE_T = 0.62;
const S = 720;
const N = 4200;
const CONF = new THREE.Vector3(2.6, 0.25, 0);

const CH_HEX = [0xf4a43c, 0x52c7be, 0xb794e0, 0xe08aa0];

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

const spreadAt = (t: number) => {
  const pre = 1.05 - 0.8 * smooth(0.4, MERGE_T, t);
  const post = 0.32 + 0.4 * smooth(MERGE_T, 1.0, t);
  return t < MERGE_T ? pre : post;
};

const buildPaths = () => {
  const exitCurve = new THREE.CubicBezierCurve3(
    CONF,
    new THREE.Vector3(6.5, 0.9, 0.7),
    new THREE.Vector3(10.5, -0.4, -0.5),
    new THREE.Vector3(16, 0.2, 0),
  );
  const channels = [
    new THREE.CubicBezierCurve3(new THREE.Vector3(-15, 4.7, -2.0), new THREE.Vector3(-7, 4.0, 2.5), new THREE.Vector3(-2, 1.6, -1.5), CONF),
    new THREE.CubicBezierCurve3(new THREE.Vector3(-15, 1.9, 2.6), new THREE.Vector3(-8, -0.6, -2.5), new THREE.Vector3(-2.5, 1.2, 2.0), CONF),
    new THREE.CubicBezierCurve3(new THREE.Vector3(-15, -2.3, -2.6), new THREE.Vector3(-7, -1.4, 2.0), new THREE.Vector3(-2, -1.4, -2.0), CONF),
    new THREE.CubicBezierCurve3(new THREE.Vector3(-15, -4.9, 1.6), new THREE.Vector3(-8, -4.0, -2.0), new THREE.Vector3(-2.5, -0.8, 1.6), CONF),
  ];
  const SPLIT = Math.floor(S * MERGE_T);
  return channels.map((cc) => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i < SPLIT; i++) pts.push(cc.getPoint(i / (SPLIT - 1)));
    for (let i = 0; i < S - SPLIT; i++) pts.push(exitCurve.getPoint(i / (S - SPLIT - 1)));
    return pts;
  });
};

const RIVER_VERT = `
  attribute vec3 aColor; attribute float aT, aSize, aSeed;
  uniform float uPR, uMerge, uPulse; uniform vec3 uMergedCol;
  varying vec3 vCol; varying float vA;
  void main(){
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    float merged = smoothstep(uMerge, uMerge + 0.05, aT);
    float pulse = 1.0 - smoothstep(0.0, 0.035, abs(aT - uPulse));
    vCol = mix(aColor, uMergedCol, merged * 0.6) * (1.0 + pulse * 1.4);
    vA = 0.42 + merged * 0.08 + pulse * 0.4;
    float size = aSize * (1.0 + merged * 0.12 + pulse * 1.1);
    gl_PointSize = size * uPR * (140.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }`;

const RIVER_FRAG = `
  varying vec3 vCol; varying float vA;
  void main(){
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.05, d) * vA;
    if (a < 0.01) discard;
    gl_FragColor = vec4(vCol, a);
  }`;

type Meta = {ch: number; t0: number; speed: number; off: THREE.Vector3; offR: number; seed: number};

const Rivers: React.FC = () => {
  const frame = useCurrentFrame();
  const time = frame / FPS;

  const {paths, meta, rivers, riverMat} = useMemo(() => {
    const pathsL = buildPaths();
    const rnd = mulberry32(42);
    const metaL: Meta[] = [];
    const pos = new Float32Array(N * 3);
    const col = new Float32Array(N * 3);
    const aT = new Float32Array(N);
    const aSize = new Float32Array(N);
    const aSeed = new Float32Array(N);
    const c = new THREE.Color();
    for (let i = 0; i < N; i++) {
      const ch = i % 4;
      const off = new THREE.Vector3(rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1).normalize();
      metaL.push({
        ch,
        t0: rnd(),
        speed: 0.018 + rnd() * 0.034,
        off,
        offR: Math.pow(rnd(), 1.6),
        seed: rnd() * 1000,
      });
      c.setHex(CH_HEX[ch]);
      col[i * 3] = c.r;
      col[i * 3 + 1] = c.g;
      col[i * 3 + 2] = c.b;
      aSize[i] = 1.1 + rnd() * 1.9;
      aSeed[i] = rnd() * 1000;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('aColor', new THREE.BufferAttribute(col, 3));
    geo.setAttribute('aT', new THREE.BufferAttribute(aT, 1));
    geo.setAttribute('aSize', new THREE.BufferAttribute(aSize, 1));
    geo.setAttribute('aSeed', new THREE.BufferAttribute(aSeed, 1));
    const merged = new THREE.Color(0xffd9a0);
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uPR: {value: 2},
        uMerge: {value: MERGE_T},
        uPulse: {value: 2.0},
        uMergedCol: {value: new THREE.Vector3(merged.r, merged.g, merged.b)},
      },
      vertexShader: RIVER_VERT,
      fragmentShader: RIVER_FRAG,
    });
    const pts = new THREE.Points(geo, mat);
    pts.position.set(2.4, -0.7, 0);
    pts.frustumCulled = false;
    return {paths: pathsL, meta: metaL, rivers: pts, riverMat: mat};
  }, []);

  // ambient motes
  const motes = useMemo(() => {
    const rnd = mulberry32(7);
    const MN = 1200;
    const mpos = new Float32Array(MN * 3);
    for (let i = 0; i < MN; i++) {
      mpos[i * 3] = (rnd() * 2 - 1) * 26;
      mpos[i * 3 + 1] = (rnd() * 2 - 1) * 14;
      mpos[i * 3 + 2] = -3 - rnd() * 14;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(mpos, 3));
    const m = new THREE.PointsMaterial({
      color: 0x8c9ecc,
      size: 0.05,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });
    const p = new THREE.Points(g, m);
    p.frustumCulled = false;
    return p;
  }, []);

  // badha pairs flickering in the depth
  const pairs = useMemo(() => {
    const rnd = mulberry32(99);
    return Array.from({length: 7}, () => {
      const cx = (rnd() * 2 - 1) * 16;
      const cy = (rnd() * 2 - 1) * 8;
      const cz = -7 - rnd() * 9;
      const dx = 0.5 + rnd() * 0.9;
      const dy = (rnd() * 2 - 1) * 0.5;
      return {
        A: new THREE.Vector3(cx - dx / 2, cy - dy / 2, cz),
        B: new THREE.Vector3(cx + dx / 2, cy + dy / 2, cz),
        phase: rnd() * 10,
        period: 6 + rnd() * 5,
      };
    });
  }, []);

  // recall pulses at fixed beats (deterministic)
  const PULSES = [120, 300];
  let uPulse = 2.0;
  for (const p0 of PULSES) {
    if (frame >= p0) {
      const p = ((frame - p0) / FPS) * 0.36;
      if (p <= 1.3) uPulse = p;
    }
  }

  // per-frame particle positions
  useLayoutEffect(() => {
    const posAttr = rivers.geometry.getAttribute('position') as THREE.BufferAttribute;
    const tAttr = rivers.geometry.getAttribute('aT') as THREE.BufferAttribute;
    const pos = posAttr.array as Float32Array;
    const aT = tAttr.array as Float32Array;
    const tmp = new THREE.Vector3();
    for (let i = 0; i < N; i++) {
      const m = meta[i];
      const t = (m.t0 + time * m.speed) % 1;
      const path = paths[m.ch];
      const f = t * (S - 1);
      const i0 = Math.floor(f);
      const i1 = Math.min(S - 1, i0 + 1);
      const fr = f - i0;
      tmp.copy(path[i0]).lerp(path[i1], fr);
      const sp = spreadAt(t) * m.offR;
      const wob = 0.16 * Math.sin(time * 0.9 + m.seed);
      pos[i * 3] = tmp.x + m.off.x * sp + wob * m.off.y;
      pos[i * 3 + 1] = tmp.y + m.off.y * sp + wob * m.off.z;
      pos[i * 3 + 2] = tmp.z + m.off.z * sp;
      aT[i] = t;
    }
    posAttr.needsUpdate = true;
    tAttr.needsUpdate = true;
    riverMat.uniforms.uPulse.value = uPulse;
  }, [frame, meta, paths, rivers, riverMat, time, uPulse]);

  return (
    <>
      <primitive object={rivers} />
      <primitive object={motes} />
      {pairs.map((pr, i) => {
        const ph = ((time + pr.phase) % pr.period) / pr.period;
        const sw = smooth(0.45, 0.58, ph);
        const slate = new THREE.Color(0x3a4358);
        const amber = new THREE.Color(0xf4a43c);
        const ca = slate.clone().lerp(amber, 1 - sw);
        const cb = slate.clone().lerp(amber, sw);
        const flash = Math.max(0, 1 - Math.abs(ph - 0.515) / 0.05) * 0.8;
        return (
          <group key={i}>
            <mesh position={pr.A}>
              <sphereGeometry args={[0.09 + (1 - sw) * 0.05, 10, 10]} />
              <meshBasicMaterial color={ca} transparent opacity={0.85} />
            </mesh>
            <mesh position={pr.B}>
              <sphereGeometry args={[0.09 + sw * 0.05, 10, 10]} />
              <meshBasicMaterial color={cb} transparent opacity={0.85} />
            </mesh>
            {flash > 0.02 && (
              <mesh position={pr.A.clone().lerp(pr.B, 0.5)}>
                <boxGeometry args={[pr.A.distanceTo(pr.B), 0.012, 0.012]} />
                <meshBasicMaterial color={0xffd9a0} transparent opacity={flash} />
              </mesh>
            )}
          </group>
        );
      })}
    </>
  );
};

const CameraRig: React.FC = () => {
  const frame = useCurrentFrame();
  const time = frame / FPS;
  const camera = useThree((s) => s.camera);
  useLayoutEffect(() => {
    const z = interpolate(frame, [0, 540], [17, 15.2]);
    camera.position.set(Math.sin(time * 0.07) * 0.5, Math.cos(time * 0.09) * 0.3, z);
    camera.lookAt(0.8, 0, 0);
  }, [camera, frame, time]);
  return null;
};

/** Screen position of the confluence point, mirroring the CameraRig math. */
const confluenceScreen = (frame: number) => {
  const time = frame / FPS;
  const z = interpolate(frame, [0, 540], [17, 15.2]);
  const eye = new THREE.Vector3(Math.sin(time * 0.07) * 0.5, Math.cos(time * 0.09) * 0.3, z);
  const fwd = new THREE.Vector3(0.8, 0, 0).sub(eye).normalize();
  const right = fwd.clone().cross(new THREE.Vector3(0, 1, 0)).normalize();
  const up = right.clone().cross(fwd);
  const rel = new THREE.Vector3(2.6 + 2.4, 0.25 - 0.7, 0).sub(eye);
  const zv = Math.max(rel.dot(fwd), 0.05);
  const f = 1080 / 2 / Math.tan(((55 / 2) * Math.PI) / 180);
  return {
    x: 1920 / 2 + (rel.dot(right) * f) / zv,
    y: 1080 / 2 - (rel.dot(up) * f) / zv,
  };
};

export const S6Sangama: React.FC = () => {
  const frame = useCurrentFrame();
  const conf = confluenceScreen(frame);

  const LABELS = [
    {at: 46, x: 130, y: 292, col: C.amber, name: 'shabda', deva: 'शब्द', sub: 'word · bm25'},
    {at: 60, x: 158, y: 452, col: C.teal, name: 'artha', deva: 'अर्थ', sub: 'meaning · vectors'},
    {at: 74, x: 158, y: 636, col: C.violet, name: 'sambandha', deva: 'सम्बन्ध', sub: 'relation · entity hop'},
    {at: 88, x: 130, y: 812, col: C.rose, name: 'kala', deva: 'काल', sub: 'time · date proximity'},
  ];

  const ringP = ramp(frame, 172, 214);
  const ringVisible = frame >= 172 && frame < 226;

  return (
    <Scene background={C.ink} fadeIn={14} fadeOut={16}>
      <AbsoluteFill>
        <ThreeCanvas
          width={1920}
          height={1080}
          camera={{fov: 55, position: [0, 0, 17], near: 0.1, far: 100}}
        >
          <fogExp2 attach="fog" args={['#0B0F1C', 0.028]} />
          <CameraRig />
          <Rivers />
        </ThreeCanvas>
      </AbsoluteFill>

      <AbsoluteFill style={{alignItems: 'center'}}>
        <Rise at={12} style={{marginTop: 92}}>
          <Kicker>
            the read path · <span style={{color: C.mute}}>smarana स्मरण</span> · every query asks four ways
          </Kicker>
        </Rise>
      </AbsoluteFill>

      {/* channel labels */}
      {LABELS.map((l) => (
        <div
          key={l.name}
          style={{
            position: 'absolute',
            left: l.x,
            top: l.y,
            opacity: ramp(frame, l.at, l.at + 20),
            transform: `translateY(${(1 - ramp(frame, l.at, l.at + 20)) * 20}px)`,
            fontFamily: F.mono,
            fontSize: 22,
            color: C.paper,
            letterSpacing: '.04em',
            textShadow: '0 2px 18px rgba(10,14,26,.95)',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: 11,
              height: 11,
              borderRadius: '50%',
              marginRight: 11,
              background: l.col,
              verticalAlign: 1,
            }}
          />
          {l.name} <Deva color={l.col}>{l.deva}</Deva>
          <small style={{display: 'block', fontSize: 14.5, color: C.mute, letterSpacing: '.1em', marginTop: 3}}>
            {l.sub}
          </small>
        </div>
      ))}

      {/* confluence — ring sits on the projected 3D point, label floats above it */}
      {ringVisible && (
        <div
          style={{
            position: 'absolute',
            left: conf.x,
            top: conf.y,
            width: 90,
            height: 90,
            border: `2px solid ${C.amber}`,
            borderRadius: '50%',
            transform: `translate(-50%,-50%) scale(${0.3 + ringP * 2.1})`,
            opacity: 0.95 * (1 - ringP),
          }}
        />
      )}
      <div
        style={{
          position: 'absolute',
          left: conf.x,
          top: conf.y - 200,
          transform: 'translateX(-50%)',
          textAlign: 'center',
          opacity: ramp(frame, 168, 190),
        }}
      >
        <div
          style={{
            fontFamily: F.display,
            fontSize: 46,
            fontWeight: 600,
            color: '#fff',
            textShadow: '0 2px 24px rgba(10,14,26,.9)',
            whiteSpace: 'nowrap',
          }}
        >
          sangama <Deva>संगम</Deva>
        </div>
        <small style={{fontFamily: F.mono, fontSize: 17.5, color: C.mute, letterSpacing: '.06em', whiteSpace: 'nowrap'}}>
          four channels · one answer
        </small>
      </div>

      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-end'}}>
        <Rise at={392} style={{marginBottom: 88}}>
          <p style={{fontFamily: F.mono, fontSize: 19, color: C.mute, letterSpacing: '.05em', margin: 0}}>
            reciprocal-rank fusion · validity annotated · packed to a fixed token budget
          </p>
        </Rise>
      </AbsoluteFill>
    </Scene>
  );
};
