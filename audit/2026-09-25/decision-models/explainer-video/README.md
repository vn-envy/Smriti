# Explainer video: Smriti's decision-model trials (2:07)

A motion explainer of why the experiment ran and what it gave back to Smriti,
built from the same numbers as `../NOTES.md`. Visuals are a time-driven HTML
page (`explainer.html`, `render(t)` sets every element for time `t`); sound is
synthesised from the page's own cue list, so picture and sound share one
timeline.

```bash
# fonts (OFL): Archivo, IBM Plex Mono, Tiro Devanagari Sanskrit from github.com/google/fonts, into ./fonts
node cues.js                                   # writes cues.json from explainer.html
node frames.js 0 3810 frames 30                # 1920x1080 JPEG frames (split the range across processes)
python audio.py                                # audio.wav: D-minor pulse bed + 20 synthesised effects
ffmpeg -framerate 30 -i frames/f%05d.jpg -i audio.wav -c:v libx264 -crf 19 -pix_fmt yuv420p \
  -c:a aac -b:a 192k -movflags +faststart -shortest smriti-judge-trials.mp4
```

The rendered MP4 (87 MB) is not committed. `poster.jpg` is a still from 1:47.
