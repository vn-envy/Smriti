import {Config} from '@remotion/cli/config';

// three.js renders reliably with the angle GL backend in headless Chrome.
Config.setChromiumOpenGlRenderer('angle');
Config.setVideoImageFormat('jpeg');
Config.setConcurrency(4);
