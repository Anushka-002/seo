"""Generate the 6 sample competitor pages used by tests and the offline CLI demo.

Run:  python sample_data/build_pages.py
"""

from pathlib import Path

TOPICS = {
    "How to choose cushioning": "Cushioning is the first thing most runners notice. Soft midsole foam absorbs impact on long easy runs, while firmer foam returns energy faster and feels more responsive at tempo pace. Heavier runners usually prefer more stack height, and runners training for races often pick a lighter, firmer shoe. Try a shoe on a treadmill before buying if the store allows it.",
    "Getting the right fit": "A good fit matters more than any feature on the spec sheet. Leave a thumb's width of space in front of your longest toe, keep the heel locked without slipping, and make sure the midfoot feels snug but never tight. Feet swell during the day and on long runs, so shop for shoes in the afternoon and wear the socks you actually run in.",
    "Road versus trail shoes": "Road shoes are built for pavement with smooth outsoles and light uppers. Trail shoes add aggressive lugs for grip on mud and rock, plus rock plates and tougher uppers to protect your feet. If you run mostly on gravel paths or park trails, a road shoe with a slightly grippier outsole is often enough.",
    "Pronation and stability": "Pronation describes how your foot rolls inward when it lands. Most runners pronate neutrally, and many modern neutral shoes work well for them. Stability shoes use guide rails or firmer medial foam to limit excess inward roll. Get a gait analysis at a running store if you have recurring knee or shin pain.",
    "Price and value": "You do not need the most expensive shoe to run well. Good daily trainers cost between 100 and 160 dollars, and last year's models are often discounted by thirty percent. Carbon plated racing shoes cost more and wear out faster, so keep them for race day rather than daily mileage.",
    "How long running shoes last": "Most running shoes last between 300 and 500 miles depending on your weight, running surface and the foam used. Signs of wear include flattened midsole creases, uneven outsole wear and new aches after runs. Rotating two pairs lets the foam recover between sessions and can extend the life of both pairs.",
    "Carbon plated racing shoes": "Carbon plated shoes combine a stiff plate with lively foam to improve running economy for many athletes. They work best at faster paces and over longer race distances. They are less stable and wear faster than daily trainers, so most coaches suggest using them for key workouts and races only.",
    "Breaking in new shoes": "Modern shoes need little break-in, but it is still wise to wear a new pair for a few short runs before a long one. Check for hot spots on the heel and toes, adjust the lacing, and replace the insole if the shoe feels slightly off. Return the shoe quickly if discomfort persists.",
}

PAGES = {
    "runnerlab.test": ("Best Running Shoes 2026: Expert Guide", list(TOPICS)[:6]),
    "milesmag.test": ("Running Shoe Buyer's Guide", [list(TOPICS)[i] for i in (0, 1, 3, 4, 5)]),
    "trailtalk.test": ("How to Pick Running Shoes", [list(TOPICS)[i] for i in (1, 2, 0, 5, 7)]),
    "racereport.test": (
        "Choosing Running Shoes for Race Day",
        [list(TOPICS)[i] for i in (6, 0, 4, 1, 5)],
    ),
    "dailyrun.test": ("Running Shoes Explained", [list(TOPICS)[i] for i in (3, 0, 1, 2, 5)]),
    "thinpage.test": ("Shoes", []),
}


SYNONYMS = [  # (original, replacement): each page applies a different subset
    ("shoes", "trainers"), ("runners", "athletes"), ("softer", "plusher"), ("firmer", "stiffer"),
    ("matters", "counts"), ("feels", "seems"), ("daily", "everyday"), ("often", "frequently"),
    ("important", "crucial"), ("improve", "boost"), ("wear out", "break down"),
    ("between", "from"), ("small", "slight"), ("check", "inspect"), ("keep", "save"),
    ("recurring", "persistent"), ("protect", "shield"), ("limit", "restrict"),
]  # fmt: skip


def paraphrase(text: str, variant: int) -> str:
    """Deterministic light rewording so pages are similar but not identical."""
    for i, (a, b) in enumerate(SYNONYMS):
        if (i + variant) % 3 == 0:
            text = text.replace(a, b)
    return text


def render(title: str, sections: list[str], variant: int = 0) -> str:
    body = "".join(f"<h2>{h}</h2><p>{paraphrase(TOPICS[h], variant)}</p>" for h in sections)
    intro = (
        "<p>Picking the right running shoes can feel overwhelming with so many models on the "
        "market. This guide walks through the choices that matter for most runners, from "
        "cushioning and fit to price and shoe lifespan, so you can buy with confidence.</p>"
        if sections
        else "<p>Buy shoes.</p>"
    )
    return (
        f"<html><head><title>{title}</title></head><body><nav>Home Shop About Login</nav>"
        f"<article><h1>{title}</h1>{intro}{body}</article>"
        "<footer>Copyright 2026 all rights reserved</footer></body></html>"
    )


if __name__ == "__main__":
    out = Path(__file__).parent / "pages"
    out.mkdir(exist_ok=True)
    for n, (domain, (title, secs)) in enumerate(PAGES.items()):
        (out / f"{domain}.html").write_text(render(title, secs, n), encoding="utf-8")
    print(f"wrote {len(PAGES)} pages to {out}")
