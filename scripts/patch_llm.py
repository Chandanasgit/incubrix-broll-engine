from pathlib import Path

def patch(path, pairs):
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        if s.count(old) != 1:
            raise SystemExit("anchor not found exactly once in %s: %s" % (path, old[:60]))
    for old, new in pairs:
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("patched", path)

patch("app/pipeline.py", [
    ("from .errors import PipelineError\n",
     "from .errors import PipelineError\nfrom .llm import LLMError, merge_queries\n"),
    ("transcribe_fn=transcribe, progress=None):",
     "transcribe_fn=transcribe, progress=None, query_writer=None):"),
    ("        scene_warn = [\"provider error: \" + e for e in errs]\n", "        scene_warn += [\"provider error: \" + e for e in errs]\n"),
    ("        cands, errs = gather(providers, qres[\"queries\"])\n",
     "        scene_warn, llm_info = [], None\n"
     "        if query_writer is not None:\n"
     "            try:\n"
     "                llm_info = query_writer.write(sc[\"text\"], avoid=avoid)\n"
     "                qres = {\"queries\": merge_queries(llm_info[\"queries\"], qres[\"queries\"]),\n"
     "                        \"notes\": qres[\"notes\"] + [\"llm queries: %s\" % llm_info[\"queries\"]]}\n"
     "            except LLMError as exc:\n"
     "                scene_warn.append(\"query LLM failed (%s); used rule-based queries\" % str(exc)[:120])\n"
     "        cands, errs = gather(providers, qres[\"queries\"])\n"),
    ("            \"reason\": reason, \"warnings\": scene_warn,\n",
     "            \"reason\": reason, \"warnings\": scene_warn,\n"
     "            \"llm\": ({\"provider\": query_writer.name, \"model\": llm_info[\"model\"],\n"
     "                     \"prompt_version\": llm_info[\"prompt_version\"], \"output\": llm_info[\"queries\"]}\n"
     "                    if llm_info else None),\n"),
    ("            \"providers\": [p.name for p in providers],\n",
     "            \"providers\": [p.name for p in providers],\n"
     "            \"query_writer\": ({\"name\": query_writer.name, \"model\": getattr(query_writer, \"model\", None),\n"
     "                              \"note\": \"scene text is sent to a third-party API\"} if query_writer else None),\n"),
])

patch("scripts/run_local.py", [
    ("from app.tts import build_tts\n", "from app.tts import build_tts\nfrom app.llm import build_query_writer\n"),
    ("a = ap.parse_args()", "ap.add_argument(\"--llm\", default=None)\na = ap.parse_args()"),
    ("common = dict(providers=build_providers(a.providers), scorer=scorer,",
     "common = dict(query_writer=build_query_writer(a.llm), providers=build_providers(a.providers), scorer=scorer,"),
])
