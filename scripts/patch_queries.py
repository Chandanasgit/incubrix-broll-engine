from pathlib import Path
p = Path("app/queries.py")
s = p.read_text(encoding="utf-8")
start = s.index("    keywords = [t for t in tokens")
end = s.index("    if not queries:\n        queries.append(\"abstract background\")")
new = '''    phrases = visual_phrases(text, exclude=used)
    if phrases is not None:
        queries.extend(phrases)
        notes.append("noun phrases used for search: %s" % phrases)
    else:
        keywords = [t for t in tokens
                    if t not in STOP and t not in used and len(t) > 2
                    and not any(ch.isdigit() for ch in t) and "%" not in t]
        keywords = _dedupe(keywords)
        if keywords:
            queries.append(" ".join(keywords[:3]))
        if len(keywords) > 3:
            queries.append(" ".join(keywords[3:6]))

'''
s = s[:start] + new + s[end:]
s = s.replace("import re\n", "import re\n\nfrom .keywords import visual_phrases\n", 1)
p.write_text(s, encoding="utf-8")
print("patched")
