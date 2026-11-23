import re

from .keywords import named_entities

SENSITIVE_WORDS = {
    "died", "death", "dead", "dies", "killed", "kill", "murder", "murdered", "funeral", "victims", "victim",
    "tragedy", "tragic", "disaster", "fire", "fires", "flood", "floods", "earthquake", "crash", "accident",
    "war", "attack", "attacks", "bombing", "shooting", "injured", "suicide", "abuse", "grief", "mourning",
    "missing", "collapsed", "explosion", "terror", "terrorist", "homeless", "disease", "cancer",
}
GRAPHIC_TERMS = {
    "fire", "fires", "burning", "blood", "bloody", "corpse", "body", "bodies", "dead", "death", "wound",
    "wounded", "injured", "explosion", "explosions", "crash", "wreck", "victim", "victims", "gun", "guns",
    "weapon", "weapons", "knife", "bomb", "bombing", "gore", "shooting", "murder", "war", "soldiers",
}
CALM_QUERIES = ["candle vigil night", "quiet street rain", "hands comforting each other"]
GENERIC_FOR = {"PERSON": "city street evening", "ORG": "modern office building"}
LABEL_WORD = {"PERSON": "person", "ORG": "brand or organisation"}


def _words(text):
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def apply_safety(text, queries, avoid=None):
    """Make the footage search safe for the narration. Returns (queries, notes).

    - Names of real people and brands are never searched; generic footage is used instead.
    - For sad or sensitive stories, graphic search terms are removed and calm footage is added.
    Every change is described in the notes, which the pipeline records as warnings.
    """
    out, notes = list(queries), []

    for name, label in named_entities(text):
        parts = {p for p in re.findall(r"[a-z0-9]+", name.lower()) if len(p) > 2}
        out = [q for q in out if not (parts & _words(q))]
        generic = GENERIC_FOR.get(label, "city street evening")
        if generic not in out:
            out.append(generic)
        notes.append("Named %s '%s' is not used in the footage search; generic footage is used instead."
                     % (LABEL_WORD.get(label, "name"), name))

    hits = sorted(_words(text) & SENSITIVE_WORDS)
    if hits:
        out = [q for q in out if not (_words(q) & GRAPHIC_TERMS)]
        out = out[:2] + [c for c in CALM_QUERIES if c not in out][:2]
        notes.append("Sensitive topic detected (%s): graphic search terms were removed and calm, "
                     "respectful footage is preferred." % ", ".join(hits[:4]))

    for term in (avoid or []):
        t = term.lower().strip()
        if t:
            out = [q for q in out if t not in q.lower()]
    if not out:
        out = ["abstract background"]
        notes.append("No safe search terms remained; a generic background query is used.")
    return out, notes
