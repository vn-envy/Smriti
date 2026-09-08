"""Remove AAC padding while preserving every rendered video frame."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which('ffmpeg')
FFPROBE = shutil.which('ffprobe')
if not FFMPEG or not FFPROBE:
    raise SystemExit('Install ffmpeg/ffprobe and make them available on PATH.')
parser = argparse.ArgumentParser()
parser.add_argument('--camera', action='store_true')
args = parser.parse_args()
stem = 'smriti-social-launch-60s-camera' if args.camera else 'smriti-social-launch-60s'
rendered = ROOT / f'out/{stem}.mp4'
output = ROOT / f'out/{stem}-exact.mp4'
mix = ROOT / 'public/user-media/social-mix.wav'
subprocess.run([
    FFMPEG, '-hide_banner', '-loglevel', 'error', '-y',
    '-i', str(rendered), '-i', str(mix), '-map', '0:v:0', '-map', '1:a:0',
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k', '-t', '60',
    '-movflags', '+faststart', str(output),
], check=True)
metadata = json.loads(subprocess.check_output([
    FFPROBE, '-v', 'error', '-show_format', '-show_streams',
    '-of', 'json', str(output),
]))
video, audio = metadata['streams']
assert float(metadata['format']['duration']) == 60
assert video['nb_frames'] == '1800' and video['r_frame_rate'] == '30/1'
assert (video['width'], video['height']) == (1920, 1080)
assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
assert audio['channels'] == 2 and audio['sample_rate'] == '48000'
measurement = subprocess.run([
    FFMPEG, '-hide_banner', '-i', str(output),
    '-af', 'loudnorm=I=-16:TP=-1.5:LRA=8:print_format=json', '-f', 'null', '-',
], capture_output=True, text=True, check=True)
levels, _ = json.JSONDecoder().raw_decode(measurement.stderr[measurement.stderr.rindex('{'):])
report = {
    'status': 'export_metadata_and_audio_measured',
    'output': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
    'metadata': metadata, 'loudness': levels,
    'source_audio_sha256': hashlib.sha256(mix.read_bytes()).hexdigest(),
    'visual_review': 'Separate human-readable root review required; metadata is not visual acceptance.',
}
(ROOT / ('out/social-camera-export-review.json' if args.camera else 'out/social-export-review.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'output': str(output), 'duration': 60,
                  'integrated_lufs': levels['input_i'], 'true_peak_dbfs': levels['input_tp']}))
