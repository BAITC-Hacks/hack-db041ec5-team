"""Encode a silent backup walkthrough from actual UI screenshots."""
from pathlib import Path
import subprocess
import imageio_ffmpeg

folder = Path(__file__).resolve().parents[1] / 'docs' / 'demo'
frames = ['01-overview.png', '02-network.png', '03-activity.png']
frames = [name for name in frames if (folder / name).is_file()]
manifest = folder / 'frames.txt'
manifest.write_text(''.join(f"file '{name}'\nduration 10\n" for name in frames) + f"file '{frames[-1]}'\n", encoding='utf-8')
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-f', 'concat', '-safe', '0', '-i', str(manifest), '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2', '-r', '25', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(folder / 'backup-demo.mp4')], check=True)
