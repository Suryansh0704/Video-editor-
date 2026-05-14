"""
edit_video.py — Video Editor
==============================
Downloads SPECIFIC audio + video artifacts by ID.
No more stale artifact problem — always edits the current run.

Edits:
  - Merges audio + video
  - Color grade (brightness, contrast, saturation)
  - Warm tone curve
  - Vignette
  - Fade in / fade out
  - Re-encodes to YouTube/Instagram spec

Output: final_video.mp4
"""

import os
import sys
import glob
import shutil
import zipfile
import subprocess
import requests
from pathlib import Path

# ══════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════

INPUT_AUDIO        = Path("output_voice.wav")
INPUT_VIDEO        = Path("raw_video.mp4")
OUTPUT_VIDEO       = Path("final_video.mp4")

TOKEN              = os.environ.get("PAT_TOKEN", "")
AUDIO_ARTIFACT_ID  = os.environ.get("AUDIO_ARTIFACT_ID", "")
VIDEO_ARTIFACT_ID  = os.environ.get("VIDEO_ARTIFACT_ID", "")

AUDIO_REPO         = "Suryansh0704/Audio-generator-"
VIDEO_REPO         = "Suryansh0704/Video-generator-"

# Edit settings
BRIGHTNESS         = 0.04
CONTRAST           = 1.10
SATURATION         = 1.25
GAMMA              = 1.05
FADE_IN            = 0.4
FADE_OUT           = 0.5

GH_HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept":        "application/vnd.github+json"
}


# ══════════════════════════════════════════════════════════════
#  SPECIFIC ARTIFACT DOWNLOADER
# ══════════════════════════════════════════════════════════════

def download_artifact_by_id(repo: str, artifact_id: str,
                              out_zip: str, extract_dir: str,
                              label: str) -> None:
    """
    Download a SPECIFIC artifact by its ID.
    This guarantees we always get the artifact from THIS run,
    not a stale one from a previous run.
    """
    if not artifact_id:
        sys.exit(f"[ERROR] {label.upper()}_ARTIFACT_ID not set")
    if not TOKEN:
        sys.exit("[ERROR] PAT_TOKEN not set")

    print(f"[{label.upper()}] Fetching artifact ID: {artifact_id}")

    # Get artifact metadata by ID
    res = requests.get(
        f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}",
        headers=GH_HEADERS
    )
    if res.status_code != 200:
        sys.exit(f"[ERROR] Artifact {artifact_id} not found: {res.status_code} {res.text[:200]}")

    artifact     = res.json()
    download_url = artifact["archive_download_url"]
    size_kb      = artifact.get("size_in_bytes", 0) // 1024
    print(f"[{label.upper()}] Name: {artifact['name']} ({size_kb}KB)")

    # Download ZIP
    r = requests.get(download_url, headers=GH_HEADERS)
    if r.status_code != 200:
        sys.exit(f"[ERROR] Download failed: {r.status_code}")

    with open(out_zip, "wb") as f:
        f.write(r.content)

    # Extract
    Path(extract_dir).mkdir(exist_ok=True)
    with zipfile.ZipFile(out_zip, "r") as z:
        z.extractall(extract_dir)
        print(f"[{label.upper()}] Extracted: {z.namelist()}")


def get_audio() -> None:
    """Download audio artifact and copy WAV to working dir."""
    download_artifact_by_id(
        AUDIO_REPO, AUDIO_ARTIFACT_ID,
        "audio.zip", "audio_extracted", "audio"
    )
    wavs = (glob.glob("audio_extracted/**/*.wav", recursive=True)
            or glob.glob("audio_extracted/*.wav"))
    if not wavs:
        sys.exit("[ERROR] No WAV file found in audio artifact")
    shutil.copy(wavs[0], str(INPUT_AUDIO))
    print(f"[AUDIO] ✅ Ready: {INPUT_AUDIO.stat().st_size // 1024}KB")


def get_video() -> None:
    """Download video artifact and copy MP4 to working dir."""
    download_artifact_by_id(
        VIDEO_REPO, VIDEO_ARTIFACT_ID,
        "video.zip", "video_extracted", "video"
    )
    mp4s = (glob.glob("video_extracted/**/*.mp4", recursive=True)
            or glob.glob("video_extracted/*.mp4"))
    if not mp4s:
        sys.exit("[ERROR] No MP4 file found in video artifact")
    shutil.copy(mp4s[0], str(INPUT_VIDEO))
    mb = INPUT_VIDEO.stat().st_size / (1024 * 1024)
    print(f"[VIDEO] ✅ Ready: {mb:.1f}MB")


# ══════════════════════════════════════════════════════════════
#  AUDIO DURATION
# ══════════════════════════════════════════════════════════════

def get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        d = float(result.stdout.strip())
        print(f"[DURATION] {path}: {d:.2f}s")
        return d
    except Exception:
        sys.exit(f"[ERROR] Could not read duration of {path}")


# ══════════════════════════════════════════════════════════════
#  EDIT PIPELINE
# ══════════════════════════════════════════════════════════════

def run_edit(duration: float) -> None:
    """
    Single ffmpeg pass:
    1. Merge audio (WAV) + video (MP4, no audio track)
    2. Color grade
    3. Warm tone curve
    4. Fade in / fade out
    5. Trim to exact audio length
    6. Encode to YouTube/Instagram spec
    """
    fade_out_start = max(0, duration - FADE_OUT)

    video_filter = ",".join([
        # Color grade
        f"eq=brightness={BRIGHTNESS}:contrast={CONTRAST}:"
        f"saturation={SATURATION}:gamma={GAMMA}",
        # Warm tone (slight orange push)
        "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/1':b='0/0 0.5/0.45 1/0.95'",
        # Vignette
        "vignette=PI/4",
        # Fade in
        f"fade=t=in:st=0:d={FADE_IN}",
        # Fade out
        f"fade=t=out:st={fade_out_start:.3f}:d={FADE_OUT}",
    ])

    cmd = [
        "ffmpeg", "-y",
        "-i", str(INPUT_VIDEO),
        "-i", str(INPUT_AUDIO),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", video_filter,
        "-t", str(duration),
        # Video — YouTube/Instagram spec
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        # Audio
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        "-shortest",
        str(OUTPUT_VIDEO)
    ]

    print("[EDIT] Running edit pipeline...")
    print(f"       Color: brightness={BRIGHTNESS} contrast={CONTRAST} "
          f"saturation={SATURATION}")
    print(f"       Fades: in={FADE_IN}s out={FADE_OUT}s")
    print(f"       Duration: {duration:.2f}s")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[ERROR] ffmpeg failed:\n{result.stderr[-600:]}")
        sys.exit(1)

    mb = OUTPUT_VIDEO.stat().st_size / (1024 * 1024)
    print(f"[✓] final_video.mp4 → {mb:.1f}MB")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 62)
    print("  Video Editor — Specific Artifact Mode")
    print(f"  Audio ID: {AUDIO_ARTIFACT_ID}")
    print(f"  Video ID: {VIDEO_ARTIFACT_ID}")
    print("=" * 62)

    # Download exact artifacts for this run
    print("\n[STEP 1] Downloading audio artifact...")
    get_audio()

    print("\n[STEP 2] Downloading video artifact...")
    get_video()

    # Get exact duration from audio
    duration = get_duration(str(INPUT_AUDIO))

    # Run edit
    print("\n[STEP 3] Editing...")
    run_edit(duration)

    print("\n" + "=" * 62)
    print("  [✓] DONE — final_video.mp4 ready")
    print("=" * 62)


if __name__ == "__main__":
    main()
