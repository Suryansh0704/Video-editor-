"""
edit_video.py — Automated Video Editor
=======================================
Fetches audio from Audio-generator- artifacts
Fetches video from Video-generator- artifacts
Merges them + adds color grade + fade in/out
Outputs: final_video.mp4
"""

import os
import sys
import json
import subprocess
import requests
import zipfile
import shutil
import glob
from pathlib import Path

INPUT_AUDIO  = Path("output_voice.wav")
INPUT_VIDEO  = Path("raw_video.mp4")
OUTPUT_VIDEO = Path("final_video.mp4")
TOKEN        = os.environ.get("PAT_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}

# ══════════════════════════════════════════════════════════════════
#  ARTIFACT DOWNLOADERS
# ══════════════════════════════════════════════════════════════════

def download_latest_artifact(repo: str, out_zip: str, extract_dir: str):
    res = requests.get(
        f"https://api.github.com/repos/Suryansh0704/{repo}/actions/artifacts",
        headers=HEADERS
    )
    artifacts = res.json().get("artifacts", [])
    if not artifacts:
        sys.exit(f"[ERROR] No artifacts found in {repo}")

    latest = artifacts[0]
    print(f"[INFO] Downloading from {repo}: {latest['name']} ({latest['size_in_bytes']} bytes)")

    r = requests.get(latest["archive_download_url"], headers=HEADERS)
    with open(out_zip, "wb") as f:
        f.write(r.content)

    with zipfile.ZipFile(out_zip, "r") as z:
        z.extractall(extract_dir)

    print(f"[INFO] Extracted to {extract_dir}")


def get_audio():
    download_latest_artifact("Audio-generator-", "audio.zip", "audio_extracted")
    wavs = glob.glob("audio_extracted/**/*.wav", recursive=True)
    if not wavs:
        wavs = glob.glob("audio_extracted/*.wav")
    if not wavs:
        sys.exit("[ERROR] No WAV found in audio artifact")
    shutil.copy(wavs[0], str(INPUT_AUDIO))
    print(f"[INFO] Audio ready: {INPUT_AUDIO} ({INPUT_AUDIO.stat().st_size} bytes)")


def get_video():
    download_latest_artifact("Video-generator-", "video.zip", "video_extracted")
    mp4s = glob.glob("video_extracted/**/*.mp4", recursive=True)
    if not mp4s:
        mp4s = glob.glob("video_extracted/*.mp4")
    if not mp4s:
        sys.exit("[ERROR] No MP4 found in video artifact")
    shutil.copy(mp4s[0], str(INPUT_VIDEO))
    print(f"[INFO] Video ready: {INPUT_VIDEO} ({INPUT_VIDEO.stat().st_size} bytes)")


# ══════════════════════════════════════════════════════════════════
#  EDITING PIPELINE
# ══════════════════════════════════════════════════════════════════

def get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def merge_and_master(video: str, audio: str, output: str):
    """
    Full edit pipeline in one ffmpeg command:
    1. Merge audio + video
    2. Color grade (brightness +0.04, contrast +1.1, saturation 1.3)
    3. Fade in (0.3s) + Fade out (0.3s)
    4. Trim to audio length
    5. Encode to YouTube/Instagram spec
    """
    duration = get_duration(audio)
    fade_out_start = duration - 0.3

    print(f"[INFO] Audio duration: {duration:.2f}s")
    print(f"[INFO] Fade out starts at: {fade_out_start:.2f}s")

    video_filter = (
        # Color grade
        f"eq=brightness=0.04:contrast=1.1:saturation=1.3,"
        # Fade in
        f"fade=t=in:st=0:d=0.3,"
        # Fade out
        f"fade=t=out:st={fade_out_start:.2f}:d=0.3"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video,
        "-i", audio,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", video_filter,
        "-t", str(duration),
        # Video encode — YouTube/Instagram spec
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        # Audio encode
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-shortest",
        output
    ]

    print("[INFO] Running edit pipeline (merge + grade + fades)...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[ERROR] ffmpeg failed:\n{result.stderr[-500:]}")
        sys.exit(1)

    size_mb = Path(output).stat().st_size / (1024 * 1024)
    print(f"[✓] Final video saved → '{output}'  ({size_mb:.1f} MB)")


# ══════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Video Editor  |  Merge + Grade + Fades")
    print("=" * 60)

    if not TOKEN:
        sys.exit("[ERROR] PAT_TOKEN not set in environment.")

    print("[INFO] Fetching audio artifact...")
    get_audio()

    print("[INFO] Fetching video artifact...")
    get_video()

    merge_and_master(str(INPUT_VIDEO), str(INPUT_AUDIO), str(OUTPUT_VIDEO))

    print("\n[✓] Done. Download final_video.mp4 from GitHub Artifacts.")


if __name__ == "__main__":
    main()
