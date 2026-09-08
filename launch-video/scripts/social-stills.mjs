import {bundle} from '@remotion/bundler';
import {openBrowser,renderStill,selectComposition} from '@remotion/renderer';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';

const root=process.cwd();
const camera=process.argv.includes('--camera');
const id=camera?'SmritiSocialCamera60':'SmritiSocial60';
const serveUrl=await bundle({entryPoint:path.join(root,'src/index.ts'),outDir:path.join(root,'out/social-bundle')});
const browser=await openBrowser('chrome',{chromiumOptions:{gl:'angle'}});
const output=path.join(root,camera?'out/social-camera-stills':'out/social-stills');await mkdir(output,{recursive:true});
const frames=camera?[76,120,159,285,339,435,549,663,728,819,879,1028,1109,1195,1239,1277,1400,1470,1599,1730]:[120,285,435,780,970,1060,1130,1180,1320,1470,1730];
try{
 const composition=await selectComposition({serveUrl,id,puppeteerInstance:browser});
 const errors=[];
 for(const frame of frames){
  await renderStill({serveUrl,composition,puppeteerInstance:browser,frame,scale:.5,output:path.join(output,`${frame}.png`),onBrowserLog:log=>{if(log.type==='error')errors.push(log);}});
  console.log(`Rendered frame ${frame}`);
 }
 await writeFile(path.join(output,'render-check.json'),JSON.stringify({composition,frames,errors},null,2));
 if(errors.length)throw new Error('Browser errors were recorded');
}finally{await browser.close({silent:true});}
