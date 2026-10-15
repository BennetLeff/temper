# video_mining

Rerunnable pipeline for turning an engineering video (teardown, design talk)
into a transcript, chapter-sliced text and a deduplicated frame set that can
be read for board-level detail.

Media never enters git: the repo is public and the footage is copyrighted.
Everything lands under `$MEDIA_ROOT/<video-id>/` (default `~/temper-media`).
Evidence documents cite frames by video timestamp, not by committed image.

    VID=Sue70X7ZeS0
    sh scripts/video_mining/fetch.sh $VID              # video + auto-captions + chapters
    sh scripts/video_mining/transcribe.sh $VID         # local Whisper transcript
    python3 -I scripts/video_mining/segments.py $VID   # per-chapter transcript slices
    sh scripts/video_mining/extract_frames.sh $VID 0 2400     # scene cuts + 1 fps in [start,end); whole video
    uv run --with pillow --with imagehash --with numpy python3 -I \
        scripts/video_mining/dedupe_frames.py $VID     # sharpest per window, drop near-duplicates
    JOBS=8 sh scripts/video_mining/stills_4k.sh $VID   # full-res stills for kept frames
    uv run --with pillow python3 -I scripts/video_mining/contact_sheets.py $VID  # per-chapter sheets
    uv run --with pillow python3 -I scripts/video_mining/triage_grids.py $VID    # 3x3 labelled grids
    # -> triage: Haiku subagents read frames/triage/grid_*.jpg and write
    #    verdicts_<x>.jsonl ({frame, category, pcb_score, engineering_score, what})
    python3 -I scripts/video_mining/merge_triage.py $VID  # verdicts.csv + shortlist.txt

Outputs in `$MEDIA_ROOT/<id>/`:

| Path | Content |
|---|---|
| `video.mkv`, `video.info.json`, `video.en.json3` | source, metadata, YouTube auto-captions |
| `whisper/video.json` | Whisper transcript with segment timings |
| `chapters/NN-slug.md` | per-chapter transcript, Whisper text with timestamps |
| `frames/raw/` | `scene_*.jpg` (scene cuts, whole video) and `dense_*.jpg` (1 fps window) |
| `frames/keep/` | deduplicated frames, named `t<seconds>.jpg` |
| `frames/index.csv` | kept frame → timestamp → chapter |
