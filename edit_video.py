"""
edit_video.py — Video Editor (Config-Aware, Shorts-Optimized)
=============================================================
Downloads SPECIFIC audio + video artifacts by ID.
Reads optimization-config.json for dynamic editing parameters.
FORCES 9:16 VERTICAL output for YouTube Shorts.

Edits:
  - Forces 1080x1920 vertical (9:16)
  - Merges audio + video
  - Color grade (brightness, contrast, saturation) — from config
  - Warm tone curve
  - Vignette
  - Fade in / fade out — from config
  - Zoom on impact — from config
  - Re-encodes to YouTube Shorts spec

Output: final_video.mp4 (1080x1920, 9:16, 60fps)
"""

import os
import sys
import glob
import shutil
import zipfile
import subprocess
import requests
import json
from pathlib import Path

# ══════════════════════════════════════════════════════════════
#  CONFIG READER (Add this at the TOP of your main file)
# ══════════════════════════════════════════════════════════════

OPT = {}
try:
    OPT = json.loads(Path("optimization-config.json").read_text())
    print(f"🧬 Using Gen {OPT.get('version', 'unknown')}")
except Exception as e:
    print("⚠️ Using defaults — optimization-config.json not found or invalid")
    OPT = {}

# ══════════════════════════════════════════════════════════════
#  DYNAMIC SETTINGS (from config with safe fallbacks)
# ══════════════════════════════════════════════════════════════

# Video edit settings — pulled from config, clamped to safe ranges
BRIGHTNESS         = max(-0.1, min(0.15, OPT.get("visual_settings", {}).get("brightness", 0.04)))
CONTRAST           = max(0.8, min(1.5, OPT.get("visual_settings", {}).get("contrast", 1.10)))
SATURATION         = max(0.5, min(2.0, OPT.get("visual_settings", {}).get("saturation", 1.25)))
GAMMA              = max(0.8, min(1.3, OPT.get("visual_settings", {}).get("gamma", 1.05)))

# Fade settings
FADE_IN            = max(0.1, min(1.0, OPT.get("visual_settings", {}).get("fade_in_seconds", 0.4)))
FADE_OUT           = max(0.1, min(1.5, OPT.get("visual_settings", {}).get("fade_out_seconds", 0.5)))

# Zoom on impact (from video-editor-config)
ZOOM_ENABLED       = OPT.get("cut_settings", {}).get("zoom_on_impact", True)
ZOOM_INTENSITY     = max(1.0, min(1.3, OPT.get("cut_settings", {}).get("zoom_intensity", 1.15)))

# Danger zone effects (from video-editor-config)
DANGER_ZONES       = OPT.get("danger_zones", [])
DANGER_EFFECTS     = OPT.get("danger_zone_effects", {})

# Text overlay settings
TEXT_ENABLED       = OPT.get("text_overlay", {}).get("enabled", True)
HIGHLIGHT_WORDS    = OPT.get("text_overlay", {}).get("highlight_keywords", 
                      ["secret", "why", "you", "never", "always", "truth", "dark", "hidden"])
FONT_SIZE          = OPT.get("text_overlay", {}).get("font_size", 48)
FONT_COLOR         = OPT.get("text_overlay", {}).get("font_color", "white")
STROKE_COLOR       = OPT.get("text_overlay", {}).get("stroke_color", "black")
STROKE_WIDTH       = OPT.get("text_overlay", {}).get("stroke_width", 3)

# Cut settings
MAX_SEGMENT        = OPT.get("cut_settings", {}).get("max_segment_duration", 3.0)
TRANSITION_STYLE   = OPT.get("cut_settings", {}).get("transition_style", "cut")

# ══════════════════════════════════════════════════════════════
#  PATHS & ENV
# ══════════════════════════════════════════════════════════════

INPUT_AUDIO        = Path("output_voice.wav")
INPUT_VIDEO        = Path("raw_video.mp4")
OUTPUT_VIDEO       = Path("final_video.mp4")

TOKEN              = os.environ.get("PAT_TOKEN", "")
AUDIO_ARTIFACT_ID  = os.environ.get("AUDIO_ARTIFACT_ID", "")
VIDEO_ARTIFACT_ID  = os.environ.get("VIDEO_ARTIFACT_ID", "")

AUDIO_REPO         = "Suryansh0704/Audio-generator-"
VIDEO_REPO         = "Suryansh0704/Video-generator-"

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
#  EDIT PIPELINE (Config-Aware + Shorts-Optimized)
# ══════════════════════════════════════════════════════════════

def build_video_filter(duration: float) -> str:
    """Build ffmpeg video filter chain — forces 9:16 vertical for Shorts."""
    fade_out_start = max(0, duration - FADE_OUT)
    
    filters = [
        # >>> STEP 1: FORCE VERTICAL 9:16 <<<
        # Scale to 1080x1920, maintain aspect ratio, pad with black bars if needed
        "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        
        # STEP 2: Color grade (from config)
        f"eq=brightness={BRIGHTNESS}:contrast={CONTRAST}:saturation={SATURATION}:gamma={GAMMA}",
        
        # STEP 3: Warm tone curve
        "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.50 1/1':b='0/0 0.5/0.45 1/0.95'",
        
        # STEP 4: Vignette
        "vignette=PI/4",
        
        # STEP 5: Fade in
        f"fade=t=in:st=0:d={FADE_IN}",
        
        # STEP 6: Fade out
        f"fade=t=out:st={fade_out_start:.3f}:d={FADE_OUT}",
    ]
    
    # Zoom on impact (subtle zoom pulse at hook points)
    if ZOOM_ENABLED:
        zoom_points = [3, 8, 13]  # Typical hook/impact timestamps
        for zp in zoom_points:
            if zp < duration - 2:
                filters.append(
                    f"zoompan=z='if(between(in\\,{zp*30}\\,{(zp+1)*30}),{ZOOM_INTENSITY},1)'"
                    f":d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                )
    
    # Danger zone effects (red flash, shake, etc.)
    for zone in DANGER_ZONES:
        start = zone.get("start_seconds", 0)
        end = zone.get("end_seconds", 0)
        effect = zone.get("effect", "none")
        
        if effect == "red_flash" and end > start:
            filters.append(
                f"colorchannelmixer=rr=1.5:gg=0.5:bb=0.5:enable='between(t\\,{start}\\,{end})'"
            )
        elif effect == "shake" and end > start:
            filters.append(
                f"geq=lum='p(X+sin(T*20)*5,Y)':enable='between(t\\,{start}\\,{end})'"
            )
    
    return ",".join(filters)


def run_edit(duration: float) -> None:
    """
    Single ffmpeg pass for YouTube Shorts:
    1. Scale to 1080x1920 (9:16 vertical)
    2. Color grade
    3. Warm tone + vignette + fades
    4. Zoom on impact
    5. Trim to exact audio length
    6. Encode to Shorts spec
    """
    video_filter = build_video_filter(duration)

    # Validate input dimensions
    probe = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(INPUT_VIDEO)
    ], capture_output=True, text=True)
    
    if probe.returncode == 0:
        w, h = map(int, probe.stdout.strip().split(','))
        print(f"[INPUT] Raw video: {w}x{h} ({'VERTICAL ✅' if h > w else 'HORIZONTAL ⚠️'})")
        if w > h:
            print("[FIX] Scaling + padding to 1080x1920 (9:16)")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(INPUT_VIDEO),
        "-i", str(INPUT_AUDIO),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", video_filter,
        "-t", str(duration),
        
        # >>> VIDEO — YOUTUBE SHORTS SPEC <<<
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",                   # Slightly higher for smaller file size
        "-profile:v", "high",
        "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-r", "60",                     # 60fps for smooth Shorts
        "-aspect", "9:16",              # Explicit 9:16 aspect ratio
        # Resolution is set in -vf filter (scale=1080:1920)
        
        # Audio
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        "-ac", "2",
        "-shortest",
        str(OUTPUT_VIDEO)
    ]

    print("[EDIT] Running Shorts edit pipeline...")
    print(f"       Config: Gen {OPT.get('version', 'default')}")
    print(f"       Color: brightness={BRIGHTNESS} contrast={CONTRAST} saturation={SATURATION}")
    print(f"       Fades: in={FADE_IN}s out={FADE_OUT}s")
    print(f"       Zoom: enabled={ZOOM_ENABLED} intensity={ZOOM_INTENSITY}")
    print(f"       Output: 1080x1920 | 9:16 | 60fps | {duration:.1f}s")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[ERROR] ffmpeg failed:\n{result.stderr[-600:]}")
        sys.exit(1)

    # Verify output is actually vertical
    out_probe = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(OUTPUT_VIDEO)
    ], capture_output=True, text=True)
    
    if out_probe.returncode == 0:
        ow, oh = map(int, out_probe.stdout.strip().split(','))
        ratio = ow / oh
        print(f"[OUTPUT] Final video: {ow}x{oh} (ratio: {ratio:.3f})")
        if ratio > 0.6:
            print("⚠️ WARNING: Output may not be 9:16! Check raw video source.")

    mb = OUTPUT_VIDEO.stat().st_size / (1024 * 1024)
    print(f"[✓] final_video.mp4 → {mb:.1f}MB")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 62)
    print("  Video Editor — Shorts Mode (1080x1920, 9:16)")
    print(f"  Config: Gen {OPT.get('version', 'default')}")
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
    print("\n[STEP 3] Editing for Shorts (9:16)...")
    run_edit(duration)

    print("\n" + "=" * 62)
    print("  [✓] DONE — final_video.mp4 ready (1080x1920)")
    print("=" * 62)


if __name__ == "__main__":
    main()
