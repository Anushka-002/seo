"""Shared tokenisation, light stemming and phrase matching."""

import re

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")

STOPWORDS = frozenset(
    """a an the and or but nor of to in on for with at by from into onto over under about as is
    are was were be been being am it its this that these those there here you your yours we our
    ours i me my they them their he she him her his not no yes so if then than too very can
    could will would should may might must shall do does did doing done have has had having just
    also more most much many some any all each every other such only own same both either
    neither what which who whom whose when where why how up down out off again further once
    s t don now get got make makes made like one two use used uses using often usually
    way ways well even still per via""".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens (apostrophes kept inside words)."""
    return _TOKEN.findall(text.lower())


def stem(token: str) -> str:
    """Very light stemmer: plural/-ies folding only, so 'shoes' ~ 'shoe', 'studies' ~ 'study'."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def stems(text: str) -> list[str]:
    """Tokenise and stem."""
    return [stem(t) for t in tokenize(text)]


def contains_phrase(text: str, phrase: str) -> bool:
    """True if the stemmed phrase appears contiguously in the stemmed text."""
    p, t = stems(phrase), stems(text)
    if not p:
        return False
    n = len(p)
    return any(t[i : i + n] == p for i in range(len(t) - n + 1))


def contains_all_terms(text: str, phrase: str) -> bool:
    """True if every non-stopword stem of the phrase appears somewhere in the text."""
    terms = {s for s in stems(phrase) if s not in STOPWORDS}
    return bool(terms) and terms <= set(stems(text))


def first_words(text: str, n: int) -> str:
    """The first n whitespace-separated words."""
    return " ".join(text.split()[:n])


def word_count(text: str) -> int:
    """Whitespace word count."""
    return len(text.split())
