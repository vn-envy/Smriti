import {MeshGradient} from '@paper-design/shaders-react';
import {ThreeCanvas} from '@remotion/three';
import React, {useMemo} from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import * as THREE from 'three';
import {C, F, FPS, mulberry32} from '../theme';
import {Deva, Kicker, Rise, Scene} from '../components/ui';

/**
 * S3 · Reveal (0:20–0:34)
 * The implosion point blooms into one amber-edged cube: one SQLite file.
 * three.js hero object over a deterministic Paper-Shaders MeshGradient.
 */

const CubeAndHalo: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const bloom = spring({frame: frame - 16, fps, config: {damping: 15, stiffness: 90, mass: 1.1}});
  const rotY = frame * 0.011;
  const rotX = 0.32 + Math.sin(frame * 0.008) * 0.06;
  const bobY = Math.sin(frame * 0.045) * 0.09;
  const camZ = interpolate(frame, [0, 420], [6.6, 5.7]);
  const corePulse = 1.6 + Math.sin(frame * 0.09) * 0.5;

  // seeded halo particles in a shell around the cube
  const halo = useMemo(() => {
    const rnd = mulberry32(2026);
    const n = 260;
    const arr = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 1.7 + rnd() * 1.9;
      const theta = rnd() * Math.PI * 2;
      const phi = Math.acos(2 * rnd() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.7;
      arr[i * 3 + 2] = r * Math.cos(phi);
    }
    return arr;
  }, []);

  const haloTexture = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const x = c.getContext('2d')!;
    const g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, 'rgba(255,217,160,1)');
    g.addColorStop(0.4, 'rgba(244,164,60,0.55)');
    g.addColorStop(1, 'rgba(244,164,60,0)');
    x.fillStyle = g;
    x.fillRect(0, 0, 64, 64);
    const tex = new THREE.CanvasTexture(c);
    return tex;
  }, []);

  const edges = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(1.15, 1.15, 1.15)), []);

  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[5, 4, 7]} intensity={40} color={C.teal} />
      <pointLight position={[-6, -3, 4]} intensity={25} color={'#6C7BD9'} />

      <group position={[0, 0.95 + bobY, 6.6 - camZ]} rotation={[rotX, rotY, 0]} scale={bloom}>
        {/* body */}
        <mesh>
          <boxGeometry args={[1.15, 1.15, 1.15]} />
          <meshStandardMaterial
            color={'#141B2D'}
            metalness={0.4}
            roughness={0.28}
            emissive={C.amber}
            emissiveIntensity={0.05}
          />
        </mesh>
        {/* amber edges */}
        <lineSegments geometry={edges}>
          <lineBasicMaterial color={C.amber} transparent opacity={0.95} />
        </lineSegments>
        {/* glowing core */}
        <mesh scale={0.26}>
          <icosahedronGeometry args={[1, 1]} />
          <meshBasicMaterial color={C.merged} />
        </mesh>
        <pointLight position={[0, 0, 0]} intensity={corePulse * 14} color={C.amber} />
      </group>

      {/* halo */}
      <group position={[0, 0.95, 6.6 - camZ]} rotation={[0.1, frame * 0.0035, 0]}>
        <points>
          <bufferGeometry>
            <bufferAttribute attach="attributes-position" args={[halo, 3]} />
          </bufferGeometry>
          <pointsMaterial
            size={0.09}
            map={haloTexture}
            transparent
            opacity={0.5 * bloom}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            color={C.merged}
          />
        </points>
      </group>
    </>
  );
};

export const S3Reveal: React.FC = () => {
  const frame = useCurrentFrame();
  const inFlash = interpolate(frame, [0, 18], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const shaderMs = (frame / FPS) * 1000 * 0.45; // slowed, deterministic

  return (
    <Scene background={C.ink} fadeIn={2} fadeOut={16}>
      {/* deterministic Paper Shaders nebula, kept deep and quiet */}
      <AbsoluteFill style={{opacity: 0.42}}>
        <MeshGradient
          colors={['#0B0F1C', '#111A33', '#1A2238', '#3A2A14']}
          distortion={0.7}
          swirl={0.55}
          speed={0}
          frame={shaderMs}
          style={{width: 1920, height: 1080}}
        />
      </AbsoluteFill>

      <AbsoluteFill>
        <ThreeCanvas
          width={1920}
          height={1080}
          camera={{fov: 42, position: [0, 0, 6.6], near: 0.1, far: 60}}
        >
          <CubeAndHalo />
        </ThreeCanvas>
      </AbsoluteFill>

      {/* copy */}
      <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-start'}}>
        <Rise at={40} style={{marginTop: 92}}>
          <Kicker>smriti's fix</Kicker>
        </Rise>
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'flex-end',
          textAlign: 'center',
          paddingBottom: 96,
        }}
      >
        <Rise at={64} dur={26}>
          <h1
            style={{
              fontFamily: F.display,
              fontWeight: 600,
              fontSize: 92,
              letterSpacing: '-0.02em',
              color: C.paper,
              margin: 0,
              lineHeight: 1.05,
            }}
          >
            one <span style={{color: C.amber}}>SQLite</span> file.
          </h1>
        </Rise>
        <Rise at={118} dur={24}>
          <p
            style={{
              fontFamily: F.mono,
              fontSize: 21,
              color: C.mute,
              margin: '26px 0 0',
              letterSpacing: '.04em',
            }}
          >
            no postgres · no neo4j · no docker · no cloud account
          </p>
        </Rise>
        <Rise at={210} dur={26}>
          <div style={{marginTop: 58}}>
            <span
              style={{
                fontFamily: F.display,
                fontWeight: 700,
                fontSize: 76,
                letterSpacing: '-0.02em',
                color: C.paper,
              }}
            >
              smriti
            </span>
            <span style={{fontFamily: F.deva, fontWeight: 500, fontSize: 58, color: C.amber, marginLeft: 22}}>
              स्मृति
            </span>
          </div>
        </Rise>
        <Rise at={244} dur={24}>
          <p style={{fontFamily: F.mono, fontSize: 17, color: C.faint, margin: '18px 0 0', letterSpacing: '.08em'}}>
            sanskrit · <Deva color={C.mute}>"that which is remembered"</Deva>
          </p>
        </Rise>
        <Rise at={300} dur={26}>
          <p
            style={{
              fontFamily: F.display,
              fontWeight: 500,
              fontSize: 40,
              color: C.mute,
              margin: '30px 0 0',
            }}
          >
            memory that knows <span style={{color: C.amber}}>when</span>.
          </p>
        </Rise>
      </AbsoluteFill>

      {/* incoming flash from S2's implosion */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 50%, rgba(255,217,160,.9), rgba(244,164,60,.5) 40%, rgba(11,15,28,0) 75%)`,
          opacity: inFlash,
          pointerEvents: 'none',
        }}
      />
    </Scene>
  );
};
