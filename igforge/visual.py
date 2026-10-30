"""Generated cover image, via the already-configured Higgsfield MCP.

I don't talk to the API by hand: I delegate to a `claude -p` with only the tools
it needs. Credentials stay where they are, and if the MCP changes, no code
changes here.
"""

import subprocess
from pathlib import Path

from . import brain, brand, store

HIGGSFIELD_TOOLS = [
    "mcp__higgsfield__generate_image_seedream",
    "mcp__higgsfield__generate_image",
    "mcp__higgsfield__generate_image_reve",
    "mcp__higgsfield__get_generation_status",
    "mcp__higgsfield__get_request_status",
]
HF_TOOLS = ["mcp__huggingface__generate_image"]


class VisualError(RuntimeError):
    pass


def _normalize(path: Path) -> None:
    """Whatever came in, a PNG with the right proportions comes out."""
    subprocess.run(
        ["sips", "-s", "format", "png", str(path), "--out", str(path)],
        capture_output=True, timeout=60,
    )


def hero(post: dict, *, provider: str = "auto", extra: str = "",
         b: dict | None = None) -> Path:
    """`auto`: Higgsfield → HuggingFace → procedural texture. The last one never fails."""
    if provider == "texture":
        return _texture(post, b)
    if provider != "auto":
        return _hero_with(post, provider, extra, b)

    problems = []
    for name in ("higgsfield", "huggingface"):
        try:
            return _hero_with(post, name, extra, b)
        except (VisualError, brain.BrainError) as e:
            problems.append(f"{name}: {e}")
    return _texture(post, b, note="; ".join(problems))


def _texture(post: dict, b: dict | None, note: str = "") -> Path:
    from . import render  # late import: render imports brand, not visual

    out = render.texture(post, b)
    post.setdefault("assets", {})["hero"] = str(out)
    post["hero_provider"] = "texture"
    if note:
        post["hero_note"] = note[:400]
    store.save_post(post)
    return out


def _hero_with(post: dict, provider: str, extra: str, b: dict | None) -> Path:
    b = b or brand.load()
    prompt_text = post.get("hero_prompt") or post.get("hook", "")
    if not prompt_text:
        raise VisualError("Missing `hero_prompt`: run `igforge write` first.")

    out = store.post_dir(post["id"]) / "hero.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    tools = (HF_TOOLS if provider == "huggingface" else HIGGSFIELD_TOOLS) + ["Bash"]
    server = "huggingface" if provider == "huggingface" else "Higgsfield"

    task = f"""Generate a single image and save it to disk.

IMAGE PROMPT (in English; use it as is, at most enrich it with the style
below):
{prompt_text}

MANDATORY STYLE: {b['visual_style']}. {extra}
FORMAT: vertical 4:5 (or the closest available). No text, no logo, no
watermark, no recognizable faces.

PROCEDURE
1. Use the {server} MCP tools to generate the image.
2. If generation is asynchronous, poll the status until it is ready.
3. Download the result to EXACTLY this path, with curl -L:
   {out}
4. Check with `ls -la` that the file exists and is larger than 10 KB.

Reply with a single line: `OK` if the file is in place, or
`FAILED: <one-line reason>`."""

    reply = brain.agent(task, tools=tools, cwd=str(out.parent), timeout=900)

    if not out.exists() or out.stat().st_size < 10_000:
        raise VisualError(f"no image produced ({provider}). The agent said: {reply[-300:]}")

    _normalize(out)
    post.setdefault("assets", {})["hero"] = str(out)
    post["hero_provider"] = provider
    store.save_post(post)
    return out
