import os

EXTRA_STOP = {"starting", "simple", "first", "next", "finally", "thing", "things", "way", "lot",
              "bit", "something", "everything", "anything", "time", "times", "week", "weeks",
              "day", "days", "year", "years", "month", "months", "today", "moment", "part"}

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load(os.getenv("SPACY_MODEL", "en_core_web_sm"), disable=["ner", "lemmatizer"])
        except Exception:
            _nlp = False
    return _nlp


def visual_phrases(text, exclude=None, max_phrases=3):
    """Short noun phrases that describe what could be filmed. None means spaCy is unavailable."""
    nlp = _get_nlp()
    if not nlp:
        return None
    exclude = exclude or set()
    doc = nlp(text)
    phrases = []
    for chunk in doc.noun_chunks:
        words, has_noun = [], False
        for t in chunk:
            w = t.text.lower()
            if t.pos_ in ("NOUN", "PROPN", "ADJ") and t.text.isalpha() and len(w) > 2 \
                    and w not in EXTRA_STOP and w not in exclude:
                words.append(w)
                has_noun = has_noun or t.pos_ in ("NOUN", "PROPN")
        if has_noun and words:
            p = " ".join(words[-3:])
            if p not in phrases:
                phrases.append(p)
    return phrases[:max_phrases]
