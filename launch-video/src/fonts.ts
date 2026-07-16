import {loadFont} from '@remotion/fonts';
import {staticFile} from 'remotion';

const fonts: Array<{family: string; file: string; weight: string}> = [
  {family: 'Space Grotesk', file: 'space-grotesk-latin-500-normal.woff2', weight: '500'},
  {family: 'Space Grotesk', file: 'space-grotesk-latin-600-normal.woff2', weight: '600'},
  {family: 'Space Grotesk', file: 'space-grotesk-latin-700-normal.woff2', weight: '700'},
  {family: 'Inter', file: 'inter-latin-400-normal.woff2', weight: '400'},
  {family: 'Inter', file: 'inter-latin-500-normal.woff2', weight: '500'},
  {family: 'Inter', file: 'inter-latin-600-normal.woff2', weight: '600'},
  {family: 'JetBrains Mono', file: 'jetbrains-mono-latin-400-normal.woff2', weight: '400'},
  {family: 'JetBrains Mono', file: 'jetbrains-mono-latin-500-normal.woff2', weight: '500'},
  {family: 'JetBrains Mono', file: 'jetbrains-mono-latin-700-normal.woff2', weight: '700'},
  {family: 'Noto Sans Devanagari', file: 'noto-sans-devanagari-devanagari-500-normal.woff2', weight: '500'},
  {family: 'Noto Sans Devanagari', file: 'noto-sans-devanagari-devanagari-600-normal.woff2', weight: '600'},
];

export const loadAllFonts = (): Promise<unknown> =>
  Promise.all(
    fonts.map((f) =>
      loadFont({
        family: f.family,
        url: staticFile(`fonts/${f.file}`),
        weight: f.weight,
      }),
    ),
  );
