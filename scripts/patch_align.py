from pathlib import Path


def patch(path, pairs):
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    if "align_script" in s or "script_text" in s:
        print("already patched:", path)
        return
    for old, new in pairs:
        if s.count(old) != 1:
            raise SystemExit("anchor not found exactly once in %s: %s" % (path, old.strip()[:70]))
    for old, new in pairs:
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("patched", path)


patch("app/pipeline.py", [
    ("from .llm import LLMError, merge_queries\n",
     "from .align import align_script\nfrom .llm import LLMError, merge_queries\n"),
    ("progress=None, query_writer=None):",
     "progress=None, query_writer=None, script_text=None):"),
    ("    scenes = split_scenes(asr[\"words\"], asr[\"duration\"], min_len=min_scene, max_len=max_scene)\n",
     "    if script_text:\n"
     "        asr[\"words\"] = align_script(script_text, asr[\"words\"], asr[\"duration\"])\n"
     "    scenes = split_scenes(asr[\"words\"], asr[\"duration\"], min_len=min_scene, max_len=max_scene)\n"),
])

patch("app/text_input.py", [
    ("res = run_pipeline(audio, out, **kw)", "res = run_pipeline(audio, out, script_text=text, **kw)"),
])
