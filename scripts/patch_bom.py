from pathlib import Path

p = Path("app/text_input.py")
s = p.read_text(encoding="utf-8")
if "ufeff" not in s:
    a = "import os\n"
    b = '    text = " ".join((script or "").split())\n'
    assert s.count(a) == 1 and s.count(b) == 1, "anchor not found in app/text_input.py"
    s = s.replace(a, "import os\nimport re\n")
    s = s.replace(b, '    cleaned = re.sub("[\\ufeff\\u200b-\\u200d\\u2060]", "", script or "")\n'
                     '    text = " ".join(cleaned.split())\n')
    p.write_text(s, encoding="utf-8")
    print("patched app/text_input.py")
else:
    print("already patched: app/text_input.py")

p = Path("scripts/batch.py")
s = p.read_text(encoding="utf-8")
n = s.count('read_text(encoding="utf-8")')
s = s.replace('read_text(encoding="utf-8")', 'read_text(encoding="utf-8-sig")')
p.write_text(s, encoding="utf-8")
print("patched scripts/batch.py (%d reads)" % n)
