"""From raw material to ideas, from ideas to finished copy."""

from datetime import datetime

from . import brain, brand, store

SYSTEM = """You are the Instagram ghostwriter for a technical founder. Write the
way they would: first person, real facts, specific details. Your only quality
bar is: would someone who does the same job stop to read this? If a sentence
could sit on anyone else's profile, it is wrong.
Never invent facts, numbers or results that are not in the material provided:
if you need a detail you don't have, rephrase instead of filling the gap.
Write all post content (hooks, captions, slides, alt text, reel lines) in the
author's content language given in the profile; JSON keys stay as specified."""

IDEAS_SCHEMA = """[
  {
    "title": "short internal title, used for the file name",
    "hook": "the first line of the post, the one visible before 'more'. Max 90 characters, must spark curiosity without clickbait",
    "angle": "in one sentence: what is this post's thesis",
    "format": "carousel | single | reel",
    "why_now": "why it makes sense to post this now, with reference to the material",
    "source": "which commits/notes back it up (brief)",
    "strength": 1-10
  }
]"""


def ideate(material: dict, n: int, b: dict | None = None) -> list[dict]:
    b = b or brand.load()
    prompt = f"""{brand.as_prompt(b)}

{material}

TASK
Propose {n} Instagram post ideas based ONLY on the material above.
Rules:
- Every idea must rest on a concrete fact from the material. No generic
  content about "building a business".
- Mix the formats: carousels for things that need explaining, single posts for
  blunt theses, reels only if there is something you can see move.
- Mix the angles: a mistake, a technical decision, a number, a personal
  why, a behind-the-scenes.
- Order from strongest to weakest and assign `strength` honestly.
- Write `title`, `hook`, `angle` and `why_now` in the content language ({b['language']}).

Response schema:
{IDEAS_SCHEMA}"""
    ideas = brain.ask_json(prompt, system=SYSTEM)
    if isinstance(ideas, dict):
        ideas = ideas.get("ideas", [])
    return [i for i in ideas if isinstance(i, dict) and i.get("hook")][:n]


def save_idea(idea: dict, material_ref: str = "") -> dict:
    post = {
        "id": store.new_id(idea.get("title") or idea["hook"]),
        "status": "idea",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "format": idea.get("format", "carousel"),
        "title": idea.get("title", ""),
        "hook": idea["hook"],
        "angle": idea.get("angle", ""),
        "why_now": idea.get("why_now", ""),
        "source": idea.get("source", ""),
        "strength": idea.get("strength"),
        "material_ref": material_ref,
        "assets": {},
    }
    store.save_post(post)
    return post


COPY_SCHEMA = """{
  "hook": "first line of the caption, max 90 characters",
  "caption": "the full caption INCLUDING the first line. Max 1400 characters. Paragraphs separated by blank lines. No hashtags in here. No em dashes.",
  "hashtags": ["#one", "#two"],
  "alt_text": "image description for accessibility, max 200 characters",
  "slides": [
    {"kicker": "short label at the top, uppercase, max 22 characters",
     "title": "big slide title, max 70 characters",
     "body": "optional body, max 180 characters, may be an empty string"}
  ],
  "reel_script": [
    {"t": "0-3s", "visual": "what you see", "vo": "what is said or read on screen"}
  ],
  "hero_prompt": "prompt in English for generating the cover image",
  "best_time": "suggested day and time, e.g. 'Tuesday 19:30', with a one-line reason"
}"""


def write(post: dict, material: str = "", b: dict | None = None,
          notes: str = "") -> dict:
    b = b or brand.load()
    fmt = post.get("format", "carousel")

    if fmt == "carousel":
        shape = ("Produce 6 to 8 slides. Slide 1 is the hook (kicker and title "
                 "only, empty body). The middle slides carry one idea each. "
                 "The last one is the close with the call to action. `reel_script` must be [].")
    elif fmt == "reel":
        shape = ("Produce a `reel_script` of 5-7 beats for 20-35 seconds total, "
                 "and `slides` with ONE single slide that serves as the reel cover.")
    else:
        shape = ("Produce `slides` with ONE single slide: it is the image of the "
                 "single post. `reel_script` must be [].")

    prompt = f"""{brand.as_prompt(b)}

THE POST TO WRITE
Format: {fmt}
Proposed hook: {post.get('hook', '')}
Thesis: {post.get('angle', '')}
Why now: {post.get('why_now', '')}
Supporting material: {post.get('source', '')}
{f"Extra directions from the author: {notes}" if notes else ""}

{material}

TASK
Write the complete post. {shape}

Non-negotiable requirements:
- Write the caption, slides, alt text and reel lines in the content language
  ({b['language']}).
- The first line of the caption must stand on its own: it is all anyone sees
  before "more".
- At least one verifiable detail (a number, a component, a file name, a
  precise error) taken from the material.
- Hashtags: at most {b['hashtags']['max']}, half niche and half broad.
  Include the core ones when relevant: {', '.join(b['hashtags']['core'])}.
- `hero_prompt` in English, consistent with this visual style:
  {b['visual_style']}. No text inside the image.

Response schema:
{COPY_SCHEMA}"""

    copy = brain.ask_json(prompt, system=SYSTEM)
    post.update({
        "caption": copy.get("caption", ""),
        "hashtags": copy.get("hashtags", []),
        "alt_text": copy.get("alt_text", ""),
        "slides": _fit_slides(copy.get("slides", []), fmt),
        "reel_script": copy.get("reel_script", []) if fmt == "reel" else [],
        "hero_prompt": copy.get("hero_prompt", ""),
        "best_time": copy.get("best_time", ""),
        "status": "draft",
    })
    post["hook"] = _hook_of(post) or copy.get("hook", post.get("hook", ""))
    store.save_post(post)
    _write_readable(post)
    return post


def critique(post: dict, b: dict | None = None) -> dict:
    """Second pass: a harsh editor who rewrites only when needed."""
    b = b or brand.load()
    prompt = f"""{brand.as_prompt(b)}

DRAFT TO JUDGE
Caption:
{post.get('caption', '')}

Hashtags: {' '.join(post.get('hashtags', []))}

Slides:
{chr(10).join(f"{i+1}. [{s.get('kicker','')}] {s.get('title','')} — {s.get('body','')}" for i, s in enumerate(post.get('slides', [])))}

TASK
Be the harsh editor. For every problem you find, actually fix it.
Look especially for: a weak first line, sentences that could sit on anyone's
profile, banned jargon, unsupported claims, slides that repeat the same idea,
a caption that runs too long.
If the draft is already good, return it nearly unchanged: don't make it worse
for the sake of changing something.
Keep the caption, slides and alt text in the content language ({b['language']}).

Reply with:
{{"verdict": "one line of honest judgment",
  "changes": ["what you changed and why"],
  "caption": "...", "hashtags": [...], "alt_text": "...",
  "slides": [{{"kicker": "...", "title": "...", "body": "..."}}]}}"""

    out = brain.ask_json(prompt, system=SYSTEM)
    post["caption"] = out.get("caption", post.get("caption", ""))
    post["hashtags"] = out.get("hashtags", post.get("hashtags", []))
    post["alt_text"] = out.get("alt_text", post.get("alt_text", ""))
    if out.get("slides"):
        post["slides"] = _fit_slides(out["slides"], post.get("format", "carousel"))
    # The editor rewrites the caption: the hook has to follow it, otherwise the
    # list and the calendar keep showing the old version.
    post["hook"] = _hook_of(post) or post.get("hook", "")
    post["edit"] = {"verdict": out.get("verdict", ""), "changes": out.get("changes", [])}
    store.save_post(post)
    _write_readable(post)
    return post


# Instagram takes 10 per carousel; beyond that it simply won't upload them.
MAX_SLIDES = {"carousel": 10, "single": 1, "reel": 1}


def _fit_slides(slides: list, fmt: str) -> list:
    """The format is a contract, not a suggestion to the model."""
    clean = [s for s in slides if isinstance(s, dict) and s.get("title")]
    return clean[:MAX_SLIDES.get(fmt, 10)]


def _hook_of(post: dict) -> str:
    for line in post.get("caption", "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _write_readable(post: dict) -> None:
    """A .md and a .txt: for copy-pasting without opening the JSON."""
    d = store.post_dir(post["id"])
    d.mkdir(parents=True, exist_ok=True)

    tags = " ".join(post.get("hashtags", []))
    (d / "caption.txt").write_text(
        post.get("caption", "").rstrip() + ("\n\n" + tags if tags else "") + "\n"
    )

    lines = [
        f"# {post.get('title') or post['hook']}",
        "",
        f"`{post['id']}` · **{post.get('format')}** · status: {post.get('status')}",
        f"Suggested time: {post.get('best_time', '—')}",
        "",
        "## Caption", "", post.get("caption", ""), "",
        f"**Hashtags** — {tags}", "",
        f"**Alt text** — {post.get('alt_text', '')}", "",
    ]
    if post.get("slides"):
        lines += ["## Slides", ""]
        for i, s in enumerate(post["slides"], 1):
            lines.append(f"**{i}. {s.get('kicker', '')}** — {s.get('title', '')}")
            if s.get("body"):
                lines.append(f"    {s['body']}")
            lines.append("")
    if post.get("reel_script"):
        lines += ["## Reel", ""]
        for beat in post["reel_script"]:
            lines.append(f"- `{beat.get('t', '')}` **{beat.get('visual', '')}** — {beat.get('vo', '')}")
        lines.append("")
    if post.get("edit"):
        lines += ["## Editor's note", "", post["edit"].get("verdict", ""), ""]
        for c in post["edit"].get("changes", []):
            lines.append(f"- {c}")
    (d / "POST.md").write_text("\n".join(lines) + "\n")
