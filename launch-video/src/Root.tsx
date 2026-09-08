import React from 'react';
import {Composition} from 'remotion';
import {SmritiLaunchVideo} from './Video';
import {FPS, TOTAL_FRAMES} from './theme';
import {SmritiEnterpriseVideo} from './enterprise/EnterpriseVideo';
import {
  FPS as EFPS, TOTAL_FRAMES as E_TOTAL_FRAMES,
} from './enterprise/etheme';
import {LaunchTeaser30} from './teaser/LaunchTeaser30';
import {SocialFilm} from './social/SocialFilm';
import {CameraFilm} from './social/CameraFilm';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="SmritiSocialCamera60" component={CameraFilm} durationInFrames={1800} fps={30} width={1920} height={1080}/>
      <Composition
        id="SmritiSocial60"
        component={SocialFilm}
        durationInFrames={1800}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="SmritiLaunch30"
        component={LaunchTeaser30}
        durationInFrames={900}
        fps={30}
        width={1920}
        height={1080}
      />
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
