import re

from .keywords import visual_phrases

STOP = set("""a an the and or but if then so of to in on at by for with from as is are was were be been being
it its this that these those there here he she they them we you i my our your his her their not no yes do does did
have has had will would can could should may might just very really more most some any all each every about into
over under up down out off than too also only own same such what which who whom when where why how make makes made
keeps keep easy get gets got""".split())

AMBIGUOUS = {
    "bank": [
        ({"money", "save", "saving", "savings", "loan", "account", "interest", "deposit", "safe", "cash", "atm"},
         "bank building finance"),
        ({"river", "water", "shore", "fishing", "stream"}, "river bank nature"),
    ],
    "cloud": [
        ({"computing", "apps", "app", "server", "servers", "data", "software", "storage", "online", "internet", "tracking"},
         "data center servers technology"),
        ({"sky", "rain", "weather", "storm", "sun", "blue"}, "clouds sky"),
    ],
    "mouse": [
        ({"computer", "click", "cursor", "keyboard", "screen", "desk"}, "computer mouse desk"),
        ({"cheese", "tiny", "animal", "pet", "rat", "squeaks"}, "small mouse animal"),
    ],
    "python": [
        ({"code", "coding", "programming", "software", "developer", "script", "data", "language"},
         "programming code laptop"),
        ({"snake", "reptile", "jungle", "slithers"}, "python snake"),
    ],
    "value": [
        ({"money", "price", "cost", "saving", "savings", "invest", "worth"}, "coins growth savings"),
    ],
}

ABSTRACT = {
    "trust": "handshake partnership",
    "slowly": "plant growing time lapse",
    "freedom": "open landscape sunrise",
    "success": "team celebrating office",
    "growth": "plant growing sunlight",
}

GROWTH_WORDS = {"grew", "growth", "increase", "increased", "rose", "rise", "up", "doubled", "surged"}


def _dedupe(items):
    seen, out = set(), []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def build_queries(text, avoid=None, max_queries=3):
    tokens = re.findall(r"[a-z0-9%']+", text.lower())
    tokset = set(tokens)
    queries, notes, used = [], [], set()

    for word, rules in AMBIGUOUS.items():
        if word not in tokset:
            continue
        used.add(word)
        for ctx, q in rules:
            if tokset & ctx:
                queries.append(q)
                notes.append("disambiguated '%s' -> '%s'" % (word, q))
                break
        else:
            notes.append("ambiguous word '%s' has no clear context; dropped from query" % word)

    if any(any(ch.isdigit() for ch in t) for t in tokens):
        if tokset & GROWTH_WORDS:
            queries.append("growth chart graph business")
        else:
            queries.append("business data charts")
        notes.append("numbers or statistics detected; using a chart-style query")

    for word, q in ABSTRACT.items():
        if word in tokset:
            queries.append(q)
            used.add(word)
            notes.append("abstract word '%s' -> '%s'" % (word, q))

    phrases = visual_phrases(text, exclude=used)
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

    if not queries:
        queries.append("abstract background")
        notes.append("no usable keywords; using a generic fallback query")

    for term in (avoid or []):
        t = term.lower().strip()
        before = len(queries)
        queries = [q for q in queries if t not in q]
        if len(queries) < before:
            notes.append("dropped query containing avoided term '%s'" % t)
    if not queries:
        queries = ["abstract background"]
        notes.append("all queries removed by avoid list; using generic fallback")

    return {"queries": _dedupe(queries)[:max_queries], "notes": notes}
