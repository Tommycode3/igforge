"""The brand kit: who you are, what you talk about, how you sound, which colors you use.

Lives in ~/.igforge/brand.json and is edited by hand. It is the only file that
really matters for output quality: the brain receives it, verbatim, on every
generation.
"""

from . import store

DEFAULT = {
    # Everything below is a placeholder. `igforge init` copies it to
    # ~/.igforge/brand.json; edit that file (`igforge brand --edit`), not this one.
    "handle": "@yourhandle",
    "name": "Your Name",
    "persona": (
        "Solo founder building a hardware product, from PCB to firmware to app. "
        "Shares the real process, including failed bring-ups and wrong footprints."
    ),
    "audience": (
        "Other technical founders, hardware and embedded engineers, people who "
        "follow build-in-public."
    ),
    "topics": [
        "building a hardware product in public",
        "self-taught PCB design",
        "embedded firmware and real-time DSP",
        "using AI agents as leverage for a solo founder",
        "expensive mistakes and what they taught me",
    ],
    "voice": {
        "tone": [
            "direct and concrete, never motivational",
            "first person, specific details and real numbers",
            "one claim per post, backed by one fact",
            "dry irony is fine, forced enthusiasm is not",
        ],
        "avoid": [
            "strings of emoji (one at most, usually none)",
            "generic hooks like 'Here are 5 lessons I learned'",
            "LinkedIn jargon: 'grateful', 'humbled', 'game-changer', 'unlock'",
            "generic hashtags like #motivation #entrepreneur",
            "promising results that were not achieved",
            "em dashes and bullet lists in the caption",
        ],
    },
    "language": "en",
    "cta": [
        "If you are building hardware alone, message me.",
        "Save this for the day you have to bring up your own board.",
        "Next step goes up here.",
    ],
    "palette": {
        "bg": "#0E0E10",
        "fg": "#FAF8F5",
        "accent": "#E8FF59",
        "muted": "#7E7E88",
        "line": "#26262C",
    },
    "font": {
        "display": '"Helvetica Neue", Helvetica, -apple-system, sans-serif',
        "mono": '"SF Mono", "Menlo", ui-monospace, monospace',
    },
    "hashtags": {
        "core": ["#buildinpublic", "#hardwarestartup", "#embedded"],
        "max": 12,
    },
    "visual_style": (
        "close-up editorial photography, hard natural light, electronics "
        "workbench, desaturated tones with a single lime accent, film grain, "
        "no text in the image, no faces"
    ),
    "sources": {
        "repos": ["~/Code"],
        "days": 21,
    },
}


def path():
    return store.HOME / "brand.json"


def load() -> dict:
    data = store.read_json(path())
    if not data:
        return dict(DEFAULT)
    merged = dict(DEFAULT)
    merged.update(data)
    return merged


def save(data: dict) -> None:
    store.write_json(path(), data)


def ensure() -> dict:
    if not path().exists():
        save(DEFAULT)
    return load()


def as_prompt(b: dict) -> str:
    """The brand kit rendered as text, exactly as the brain reads it."""
    tone = "\n".join(f"- {t}" for t in b["voice"]["tone"])
    avoid = "\n".join(f"- {t}" for t in b["voice"]["avoid"])
    topics = "\n".join(f"- {t}" for t in b["topics"])
    return f"""AUTHOR PROFILE
Name: {b['name']} ({b['handle']})
Who they are: {b['persona']}
Who they write for: {b['audience']}
Content language: {b['language']} (all post text must be written in this language)

TOPICS THEY COVER
{topics}

HOW THEY SOUND
{tone}

NEVER DO
{avoid}

TYPICAL SIGN-OFFS (vary them, do not copy verbatim)
{chr(10).join('- ' + c for c in b['cta'])}
"""
