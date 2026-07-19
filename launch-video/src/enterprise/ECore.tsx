import {ThreeCanvas} from '@remotion/three';
import {useFrame, useThree} from '@react-three/fiber';
import React, {useLayoutEffect, useMemo, useRef} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import * as THREE from 'three';
import {E, mulberry32} from './etheme';

/**
 * The 3D hero shot — "the memory core".
 *
 * All geometry is procedural (icosahedron, torus, instanced shards): no
 * downloaded assets, no licences, no binary blobs in the repo. That is the
 * same principle the product ships on, applied to the film.
 *
 * Reads: one crystalline core (the SQLite file) wrapped in three rotating
 * rings (world time · knowledge time · lifecycle), with receipt shards
 * streaming in and locking into a verified lattice.
 */

const COL = {
  amber: new THREE.Color(E.amber),
  teal: new THREE.Color(E.teal),
  violet: new THREE.Color(E.violet),
  rose: new THREE.Color(E.rose),
};

const SHARDS = 220;

const Core: React.FC<{t: number}> = ({t}) => {
  const core = useRef<THREE.Mesh>(null);
  const glow = useRef<THREE.Mesh>(null);
  const rings = useRef<THREE.Group>(null);
  const shards = useRef<THREE.InstancedMesh>(null);

  const shardData = useMemo(() => {
    const rnd = mulberry32(99);
    return Array.from({length: SHARDS}, () => {
      const a = rnd() * Math.PI * 2;
      const rad = 5.5 + rnd() * 7;
      const y = (rnd() - 0.5) * 7;
      return {
        a, rad, y,
        spin: 0.4 + rnd() * 1.4,
        scale: 0.07 + rnd() * 0.13,
        delay: rnd() * 0.42,
        tilt: rnd() * Math.PI,
        col: [COL.amber, COL.teal, COL.violet, COL.rose][Math.floor(rnd() * 4)],
      };
    });
  }, []);

  useFrame(() => {
    const ease = 1 - Math.pow(1 - Math.min(1, t / 0.72), 3);

    if (core.current) {
      core.current.rotation.y = t * 2.1;
      core.current.rotation.x = Math.sin(t * 3.1) * 0.22;
      const pulse = 1 + Math.sin(t * Math.PI * 2 * 8) * 0.02 * ease; // ~beat
      core.current.scale.setScalar((0.35 + ease * 0.65) * pulse);
    }
    if (glow.current) {
      glow.current.scale.setScalar(1.5 + Math.sin(t * Math.PI * 2 * 4) * 0.06);
      (glow.current.material as THREE.MeshBasicMaterial).opacity = 0.10 + ease * 0.12;
    }
    if (rings.current) {
      rings.current.rotation.y = t * 0.9;
      rings.current.children.forEach((c, i) => {
        c.rotation.z = t * (0.7 + i * 0.45) * (i % 2 ? -1 : 1);
        c.rotation.x = Math.PI / 2.6 + i * 0.55 + Math.sin(t * 1.4 + i) * 0.12;
        const s = 1 + i * 0.42;
        c.scale.setScalar(s * (0.5 + ease * 0.5));
      });
    }
    if (shards.current) {
      const dummy = new THREE.Object3D();
      shardData.forEach((s, i) => {
        // shards fly in from the rim and lock into a shell = "verified lattice"
        const p = Math.min(1, Math.max(0, (t - s.delay) / 0.55));
        const eased = 1 - Math.pow(1 - p, 4);
        const r = s.rad - (s.rad - 3.1) * eased;
        const ang = s.a + t * s.spin * (1 - eased * 0.75);
        dummy.position.set(Math.cos(ang) * r, s.y * (1 - eased * 0.55), Math.sin(ang) * r);
        dummy.rotation.set(s.tilt + t * 1.6, ang, s.tilt * 0.5);
        dummy.scale.setScalar(s.scale * (0.4 + eased * 0.6));
        dummy.updateMatrix();
        shards.current!.setMatrixAt(i, dummy.matrix);
        shards.current!.setColorAt(i, s.col);
      });
      shards.current.instanceMatrix.needsUpdate = true;
      if (shards.current.instanceColor) shards.current.instanceColor.needsUpdate = true;
    }
  });

  return (
    <>
      <ambientLight intensity={1.5} />
      <directionalLight position={[6, 8, 6]} intensity={2.2} color="#ffffff" />
      <directionalLight position={[-7, -3, -5]} intensity={1.1} color={E.violet} />
      <pointLight position={[0, 0, 0]} intensity={3.2} color={E.amber} distance={14} />

      {/* the file itself: a crystal that refracts everything around it */}
      <mesh ref={core}>
        <icosahedronGeometry args={[1.9, 1]} />
        <meshPhysicalMaterial
          color="#ffffff" metalness={0.1} roughness={0.08}
          transmission={0.86} thickness={2.4} ior={1.6}
          clearcoat={1} clearcoatRoughness={0.05}
          iridescence={0.9} iridescenceIOR={1.8}
          attenuationColor={new THREE.Color(E.amber)} attenuationDistance={3.2}
        />
      </mesh>

      <mesh ref={glow}>
        <sphereGeometry args={[2.1, 32, 32]} />
        <meshBasicMaterial color={E.amber} transparent opacity={0.14} side={THREE.BackSide} />
      </mesh>

      {/* three rings = three time axes */}
      <group ref={rings}>
        {[COL.amber, COL.teal, COL.violet].map((c, i) => (
          <mesh key={i}>
            <torusGeometry args={[3.0, 0.035 + i * 0.008, 12, 160]} />
            <meshBasicMaterial color={c} transparent opacity={0.85 - i * 0.16} />
          </mesh>
        ))}
      </group>

      {/* receipts locking into a verified shell */}
      <instancedMesh ref={shards} args={[undefined, undefined, SHARDS]}>
        <octahedronGeometry args={[1, 0]} />
        <meshStandardMaterial
          metalness={0.35} roughness={0.25} transparent opacity={0.92}
          emissiveIntensity={0.4} emissive="#ffffff"
        />
      </instancedMesh>
    </>
  );
};

const Rig: React.FC<{t: number}> = ({t}) => {
  const {camera} = useThree();
  useLayoutEffect(() => {
    camera.position.set(0, 0.6, 13.5);
    camera.lookAt(0, 0, 0);
  }, [camera]);
  useFrame(() => {
    // slow Apple-style dolly + parallax orbit
    const z = 13.5 - 4.6 * (1 - Math.pow(1 - Math.min(1, t / 0.9), 3));
    const a = t * 0.42;
    camera.position.set(Math.sin(a) * 2.4, 0.6 + Math.sin(t * 1.1) * 0.5, z);
    camera.lookAt(0, 0, 0);
  });
  return null;
};

export const CoreCanvas: React.FC<{progress: number}> = ({progress}) => {
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill>
      <ThreeCanvas
        width={width}
        height={height}
        gl={{antialias: true, alpha: true}}
        style={{background: 'transparent'}}
      >
        <Rig t={progress} />
        <Core t={progress} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
