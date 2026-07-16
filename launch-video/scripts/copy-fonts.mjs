// Copies the exact woff2 files the film uses from @fontsource packages
// into public/fonts. Runs automatically after `npm install` (postinstall).
import {copyFileSync, mkdirSync, existsSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'public', 'fonts');
mkdirSync(out, {recursive: true});

const files = [
  ['@fontsource/space-grotesk', 'space-grotesk-latin-500-normal.woff2'],
  ['@fontsource/space-grotesk', 'space-grotesk-latin-600-normal.woff2'],
  ['@fontsource/space-grotesk', 'space-grotesk-latin-700-normal.woff2'],
  ['@fontsource/inter', 'inter-latin-400-normal.woff2'],
  ['@fontsource/inter', 'inter-latin-500-normal.woff2'],
  ['@fontsource/inter', 'inter-latin-600-normal.woff2'],
  ['@fontsource/jetbrains-mono', 'jetbrains-mono-latin-400-normal.woff2'],
  ['@fontsource/jetbrains-mono', 'jetbrains-mono-latin-500-normal.woff2'],
  ['@fontsource/jetbrains-mono', 'jetbrains-mono-latin-700-normal.woff2'],
  ['@fontsource/noto-sans-devanagari', 'noto-sans-devanagari-devanagari-500-normal.woff2'],
  ['@fontsource/noto-sans-devanagari', 'noto-sans-devanagari-devanagari-600-normal.woff2'],
];

let copied = 0;
for (const [pkg, file] of files) {
  const src = join(root, 'node_modules', pkg, 'files', file);
  if (existsSync(src)) {
    copyFileSync(src, join(out, file));
    copied++;
  } else {
    console.warn(`[copy-fonts] missing: ${src}`);
  }
}
console.log(`[copy-fonts] copied ${copied}/${files.length} font files → public/fonts`);
