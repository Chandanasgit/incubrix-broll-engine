import difflib
import re


def _norm(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def _spread(tokens, t0, t1):
    """Give each token a time slot inside [t0, t1], sized by its length."""
    t1 = max(t1, t0)
    weights = [max(1, len(_norm(t))) for t in tokens]
    total = float(sum(weights))
    out, cur = [], t0
    for tok, w in zip(tokens, weights):
        nxt = cur + (t1 - t0) * w / total
        out.append({"word": " " + tok, "start": cur, "end": nxt})
        cur = nxt
    return out


def align_script(script, asr_words, duration):
    """Words of the written script, timed from the transcription of its own narration.

    The transcription can mishear words, so the text always comes from the script;
    the transcription only supplies when each word is spoken.
    """
    tokens = script.split()
    if not tokens or not asr_words:
        return []
    a = [_norm(t) for t in tokens]
    b = [_norm(w["word"]) for w in asr_words]
    out = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            continue
        chunk = tokens[i1:i2]
        if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
            for k, tok in enumerate(chunk):
                w = asr_words[j1 + k]
                out.append({"word": " " + tok, "start": float(w["start"]), "end": float(w["end"])})
        elif tag == "replace":
            out += _spread(chunk, float(asr_words[j1]["start"]), float(asr_words[j2 - 1]["end"]))
        else:  # delete: script words that were not heard
            t0 = float(asr_words[j1 - 1]["end"]) if j1 > 0 else 0.0
            t1 = float(asr_words[j1]["start"]) if j1 < len(asr_words) else float(duration)
            out += _spread(chunk, t0, t1)
    prev = 0.0
    for w in out:  # keep times in order
        w["start"] = max(w["start"], prev)
        w["end"] = max(w["end"], w["start"])
        prev = w["end"]
    return out
