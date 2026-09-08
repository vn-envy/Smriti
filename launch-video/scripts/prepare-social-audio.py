"""Prepare the user's local launch-film assets without committing source media."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--assets-dir', type=Path, default=Path.home() / 'Downloads')
DOWNLOADS = parser.parse_args().assets_dir
DEST = ROOT / 'public/user-media'
DEST.mkdir(parents=True, exist_ok=True)
sources = {
    'groove.mp3': DOWNLOADS / 'Funky_Launch_Groove-53a7553e-4c2e-45c1-8f10-d947eb6d68af.mp3',
    'technology.wav': DOWNLOADS / 'futuristic-technology-presentation-inspiring-ai-2026-06-30-00-56-58-utc/wav/Tech Futuristic Product Informative AI (60 sec).wav',
    'notification.wav': DOWNLOADS / 'ui-notification-2026-05-18-21-05-22-utc/UI Notification 1.wav',
}
for name, source in sources.items():
    shutil.copyfile(source, DEST / name)
for archive, member, target in [
    ('keyboard-button-press-and-click-2026-06-17-21-16-10-utc.zip', 'Keyboard Button Press SFX/Keyboard_button_01.wav', 'key.wav'),
    ('keyboard-typing-2026-05-18-17-43-55-utc.zip', 'Mountain Audio - Typing Sequence (Room).wav', 'typing.wav'),
]:
    with zipfile.ZipFile(DOWNLOADS / archive) as z:
        (DEST / target).write_bytes(z.read(member))

# A short, quiet technology texture opens into the main groove. Effects mark
# the written update, the retained record, the time cursor, and the result.
graph = (
    '[0:a]atrim=start=0.12:end=60.12,asetpts=PTS-STARTPTS,volume=0.90,'
    'afade=t=in:d=0.18,afade=t=out:st=58.2:d=1.8[bed];'
    '[1:a]atrim=0:3,asetpts=PTS-STARTPTS,volume=0.09,'
    'afade=t=in:d=0.12,afade=t=out:st=1:d=2[texture];'
    '[2:a]atrim=0:1.6,asetpts=PTS-STARTPTS,volume=0.35,'
    'afade=t=out:st=1.3:d=0.3,adelay=1300|1300[typing];'
    '[3:a]atrim=0:0.6,asetpts=PTS-STARTPTS,volume=0.5,asplit=2[k1][k2];'
    '[k1]adelay=34000|34000[key1];[k2]adelay=37200|37200[key2];'
    '[4:a]atrim=0:1.4,asetpts=PTS-STARTPTS,volume=0.22,asplit=2[n1][n2];'
    '[n1]adelay=11200|11200[notice1];[n2]adelay=51000|51000[notice2];'
    '[bed][texture][typing][key1][key2][notice1][notice2]'
    'amix=inputs=7:duration=first:normalize=0,alimiter=limit=0.84:level=false,'
    'aformat=sample_rates=48000:channel_layouts=stereo[out]'
)
ffmpeg = shutil.which('ffmpeg')
if not ffmpeg:
    raise SystemExit('Install ffmpeg and make it available on PATH.')
command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
for name in ['groove.mp3', 'technology.wav', 'typing.wav', 'key.wav', 'notification.wav']:
    command += ['-i', str(DEST / name)]
command += ['-filter_complex', graph, '-map', '[out]', '-t', '60',
            '-c:a', 'pcm_s24le', str(DEST / 'social-mix.wav')]
subprocess.run(command, check=True)
manifest = {
    'duration_seconds': 60, 'source_media_committed': False,
    'files_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in DEST.iterdir() if p.is_file()},
    'filter_graph': graph,
    'cues_seconds': {'typing': 1.3, 'record_reveal': 11.2,
                     'time_cursor': [34, 37.2], 'measurement_result': 51},
}
(ROOT / 'social-audio-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
