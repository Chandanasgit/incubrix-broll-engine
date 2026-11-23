from pathlib import Path

p = Path("app/pipeline.py")
s = p.read_text(encoding="utf-8")
if "apply_safety" in s:
    print("already patched: app/pipeline.py")
else:
    a = "from .llm import LLMError, merge_queries\n"
    b = '        cands, errs = gather(providers, qres["queries"])\n'
    assert s.count(a) == 1 and s.count(b) == 1, "anchor not found in app/pipeline.py"
    s = s.replace(a, a + "from .safety import apply_safety\n")
    s = s.replace(b,
        '        safe_queries, safety_notes = apply_safety(sc["text"], qres["queries"], avoid=avoid)\n'
        '        qres = {"queries": safe_queries, "notes": qres["notes"] + safety_notes}\n'
        '        scene_warn += safety_notes\n' + b)
    p.write_text(s, encoding="utf-8")
    print("patched app/pipeline.py")
