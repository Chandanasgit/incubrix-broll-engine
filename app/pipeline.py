import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from .asr import transcribe
from .errors import PipelineError
from .align import align_script
from .llm import LLMError, merge_queries
from .safety import apply_safety
from .fallback import make_fallback_clip
from .providers.base import Clip
from .queries import build_queries
from .ranker import choose_clip, gather
from .render import (RATIOS, RenderError, concat, describe, download_clip,
                     finalize, make_srt, normalise_scene, probe)
from .scenes import split_scenes


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _ver(pkg):
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "unknown"


def _json_default(o):
    try:
        return float(o)
    except (TypeError, ValueError):
        return str(o)


def _write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, default=_json_default), encoding="utf-8")


def run_pipeline(audio_path, out_dir, *, providers, scorer, ratios=("16:9",), avoid=None,
                 captions=None, job_id=None, transcribe_fn=transcribe, progress=None, query_writer=None, script_text=None):
    t_start = time.time()
    job_id = job_id or uuid.uuid4().hex[:12]
    captions = captions or {"burn_in": True, "srt": True}
    progress = progress or (lambda pct, msg: None)
    max_audio = _env_float("MAX_AUDIO_SECONDS", 600)
    min_scene = _env_float("MIN_SCENE_SECONDS", 2.5)
    max_scene = _env_float("MAX_SCENE_SECONDS", 8.0)
    out = Path(out_dir)
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    warnings, timings = [], {}

    for r in ratios:
        if r not in RATIOS:
            raise PipelineError("INVALID_ASPECT_RATIO", "Unsupported aspect ratio: %s" % r,
                                details={"allowed": sorted(RATIOS)})

    progress(2, "checking input")
    try:
        info = probe(audio_path)
    except RenderError:
        raise PipelineError("UNSUPPORTED_MEDIA", "The input is not a readable audio file.")
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        raise PipelineError("NO_AUDIO_STREAM", "The input file contains no audio.")
    in_dur = float(info.get("format", {}).get("duration", 0) or 0)
    if in_dur > max_audio:
        raise PipelineError("AUDIO_TOO_LONG", "Audio is longer than the allowed maximum.",
                            details={"max_seconds": max_audio, "got_seconds": round(in_dur, 1)})

    progress(5, "transcribing")
    t = time.time()
    asr = transcribe_fn(str(audio_path))
    timings["asr_s"] = round(time.time() - t, 2)
    if not asr["words"]:
        raise PipelineError("NO_SPEECH_DETECTED", "No speech was found in the audio.")

    if script_text:
        asr["words"] = align_script(script_text, asr["words"], asr["duration"])
    scenes = split_scenes(asr["words"], asr["duration"], min_len=min_scene, max_len=max_scene)
    progress(10, "found %d scenes" % len(scenes))

    t = time.time()
    used, timeline, src_paths = set(), [], []
    for i, sc in enumerate(scenes):
        progress(10 + int(50 * i / len(scenes)), "choosing footage for scene %d of %d" % (i + 1, len(scenes)))
        qres = build_queries(sc["text"], avoid=avoid)
        scene_warn, llm_info = [], None
        if query_writer is not None:
            try:
                llm_info = query_writer.write(sc["text"], avoid=avoid)
                qres = {"queries": merge_queries(llm_info["queries"], qres["queries"]),
                        "notes": qres["notes"] + ["llm queries: %s" % llm_info["queries"]]}
            except LLMError as exc:
                scene_warn.append("query LLM failed (%s); used rule-based queries" % str(exc)[:120])
        safe_queries, safety_notes = apply_safety(sc["text"], qres["queries"], avoid=avoid)
        qres = {"queries": safe_queries, "notes": qres["notes"] + safety_notes}
        scene_warn += safety_notes
        cands, errs = gather(providers, qres["queries"])
        scene_warn += ["provider error: " + e for e in errs]
        sdur = sc["end"] - sc["start"]
        src = work / ("src_%d.mp4" % i)
        clip, score, scorer_name, reason = None, None, None, None

        for _ in range(3):
            pick = choose_clip(sc["text"], cands, scorer, used, min_duration=sdur) if cands else None
            if pick is None:
                break
            cand = pick["clip"]
            used.add((cand.provider, cand.clip_id))
            try:
                download_clip(cand.download_url, src)
            except RenderError as exc:
                scene_warn.append("clip %s/%s unusable: %s" % (cand.provider, cand.clip_id, str(exc)[:120]))
                continue
            clip, score, scorer_name = cand, pick["score"], pick["scorer"]
            scene_warn += pick["notes"]
            if score is None:
                reason = "first result (scoring failed); %d candidates" % pick["considered"]
            else:
                reason = "best of %d candidates by %s score %.3f for queries %s" % (
                    pick["considered"], scorer_name, score, qres["queries"])
            break

        if clip is None:
            make_fallback_clip(src, i)
            clip = Clip(provider="fallback", clip_id="fallback-%d" % i, page_url="", download_url="",
                        thumbnail_url="", width=1280, height=720, duration=10.0, tags=[],
                        licence="Generated locally; contains no third-party media", attribution="")
            reason = "no usable footage found; generated plain background"
            scene_warn.append("fallback background used")

        src_paths.append(src)
        timeline.append({
            "index": i, "text": sc["text"], "start": sc["start"], "end": sc["end"],
            "queries": qres["queries"], "query_notes": qres["notes"],
            "clip": clip.to_dict(), "relevance_score": score, "scorer": scorer_name,
            "reason": reason, "warnings": scene_warn,
            "llm": ({"provider": query_writer.name, "model": llm_info["model"],
                     "prompt_version": llm_info["prompt_version"], "output": llm_info["queries"]}
                    if llm_info else None),
        })
        warnings += ["scene %d: %s" % (i, w) for w in scene_warn]
    timings["footage_s"] = round(time.time() - t, 2)

    srt_text = make_srt(asr["words"])
    (work / "captions.srt").write_text(srt_text, encoding="utf-8")
    if captions.get("srt"):
        (out / "captions.srt").write_text(srt_text, encoding="utf-8")

    t = time.time()
    outputs, checks = {}, {}
    try:
        for ri, ratio in enumerate(ratios):
            progress(60 + int(35 * ri / len(ratios)), "rendering %s" % ratio)
            tag = ratio.replace(":", "x")
            parts = []
            for i, sc in enumerate(scenes):
                part = work / ("scene_%d_%s.mp4" % (i, tag))
                normalise_scene(src_paths[i], sc["end"] - sc["start"], ratio, part)
                parts.append(part)
            joined = concat(parts, work / ("joined_%s.mp4" % tag))
            final = finalize(joined, audio_path, out / ("video_%s.mp4" % tag),
                             srt=work / "captions.srt", burn_in=bool(captions.get("burn_in")), ratio=ratio)
            d = describe(final)
            problems = []
            if (d["width"], d["height"]) != RATIOS[ratio]:
                problems.append("unexpected size")
            if abs(d["duration"] - asr["duration"]) > 0.3:
                problems.append("duration differs from narration by more than 0.3 s")
            if not d["has_audio"]:
                problems.append("no audio track")
            checks[ratio] = dict(d, ok=not problems, problems=problems)
            outputs[ratio] = final.name
            warnings += ["%s: %s" % (ratio, p) for p in problems]
    except RenderError as exc:
        raise PipelineError("RENDER_FAILED", "Rendering failed: " + str(exc)[:300], retryable=True)
    timings["render_s"] = round(time.time() - t, 2)
    timings["total_s"] = round(time.time() - t_start, 2)

    _write_json(out / "timeline.json", {"job_id": job_id, "duration": asr["duration"], "scenes": timeline})
    manifest = {
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": {"file": Path(audio_path).name, "duration_s": asr["duration"], "scenes": len(scenes)},
        "models": {
            "asr": {"name": "faster-whisper " + os.getenv("WHISPER_MODEL", "base"), "version": _ver("faster-whisper")},
            "ranker": {"name": scorer.name, "model": getattr(scorer, "model_name", None),
                       "weights": getattr(scorer, "pretrained", None), "version": _ver("open_clip_torch")},
            "providers": [p.name for p in providers],
            "query_writer": ({"name": query_writer.name, "model": getattr(query_writer, "model", None),
                              "note": "scene text is sent to a third-party API"} if query_writer else None),
        },
        "settings": {"ratios": list(ratios), "avoid": avoid or [], "captions": captions,
                     "min_scene_seconds": min_scene, "max_scene_seconds": max_scene},
        "seed": None,
        "seed_note": "No randomness is used; output depends only on the input and footage search results.",
        "timings": timings,
        "cost_estimate_usd": 0.0,
        "cost_note": "Local models and free footage APIs; compute cost not included.",
        "warnings": warnings,
        "rights": {
            "commercial_use_ok": not any(s["clip"]["provider"] == "mock" for s in timeline),
            "ai_generated_clips": sum(1 for s in timeline if s["clip"]["ai_generated"]),
            "clips": [{"provider": s["clip"]["provider"], "clip_id": s["clip"]["clip_id"],
                       "licence": s["clip"]["licence"], "attribution": s["clip"]["attribution"],
                       "page_url": s["clip"]["page_url"]} for s in timeline],
        },
        "outputs": outputs,
        "checks": checks,
    }
    _write_json(out / "manifest.json", manifest)
    if os.getenv("KEEP_WORK", "0") != "1":
        shutil.rmtree(work, ignore_errors=True)
    progress(100, "done")
    return {"job_id": job_id, "outputs": outputs, "warnings": warnings, "timings": timings}
