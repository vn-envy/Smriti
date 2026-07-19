import React from 'react';
import {Composition} from 'remotion';
import {SmritiLaunchVideo} from './Video';
import {FPS, TOTAL_FRAMES} from './theme';
import {SmritiEnterpriseVideo} from './enterprise/EnterpriseVideo';
import {
  FPS as EFPS, TOTAL_FRAMES as E_TOTAL_FRAMES,
} from './enterprise/etheme';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="SmritiLaunch"
        component={SmritiLaunchVideo}
        durationInFrames={TOTAL_FRAMES}
        fps={FPS}
        width={1920}
        height={1080}
      />
      <Composition
        id="SmritiEnterprise"
        component={SmritiEnterpriseVideo}
        durationInFrames={E_TOTAL_FRAMES}
        fps={EFPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
