SENT_END = (".", "!", "?", "\u0964")
PHRASE_END = (",", ";", ":")


def _dur(chunk):
    return chunk[-1]["end"] - chunk[0]["start"]


def _split_long(sentence, min_len, max_len):
    if _dur(sentence) <= max_len:
        return [sentence]
    out, cur = [], []
    for i, w in enumerate(sentence):
        cur.append(w)
        rest = sentence[i + 1:]
        if (w["word"].strip().endswith(PHRASE_END) and _dur(cur) >= min_len
                and rest and _dur(rest) >= min_len):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def split_scenes(words, duration, min_len=2.5, max_len=8.0):
    if not words:
        return []
    sentences, cur = [], []
    for w in words:
        cur.append(w)
        if w["word"].strip().endswith(SENT_END):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)

    chunks = []
    for s in sentences:
        chunks.extend(_split_long(s, min_len, max_len))

    merged = []
    for c in chunks:
        if merged and _dur(c) < min_len:
            merged[-1].extend(c)
        else:
            merged.append(list(c))
    if len(merged) > 1 and _dur(merged[0]) < min_len:
        merged[1] = merged[0] + merged[1]
        merged.pop(0)

    scenes = []
    for i, c in enumerate(merged):
        start = 0.0 if i == 0 else c[0]["start"]
        scenes.append({
            "index": i,
            "text": "".join(w["word"] for w in c).strip(),
            "start": round(start, 3),
            "end": round(c[-1]["end"], 3),
        })
    for i in range(len(scenes) - 1):
        scenes[i]["end"] = scenes[i + 1]["start"]
    scenes[-1]["end"] = round(duration, 3)
    return scenes
