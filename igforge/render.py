"""The slides: branded HTML → PNG via headless Chrome.

Deterministic and free. Generative stuff is left to the cover image
(visual.py); what matters here is that the typography is always the same.
"""

import base64
import hashlib
import html
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import brand, store

SIZES = {"carousel": (1080, 1350), "single": (1080, 1350), "reel": (1080, 1920)}

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


class RenderError(RuntimeError):
    pass


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RenderError(
        "A Chromium browser is needed to rasterize the slides. "
        "Install Google Chrome, or use `igforge export` and lay them out by hand."
    )


def _fit(text: str, steps: list[tuple[int, int]]) -> int:
    n = len(text or "")
    for limit, size in steps:
        if n <= limit:
            return size
    return steps[-1][1]


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, bl = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{bl},{alpha})"


def _data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def slide_html(slide: dict, *, index: int, total: int, b: dict,
               size: tuple[int, int], background: Path | None = None,
               soft_background: bool = False) -> str:
    p, f = b["palette"], b["font"]
    w, h = size
    cover = index == 1
    kicker = html.escape(slide.get("kicker", "") or "")
    title = html.escape(slide.get("title", "") or "")
    body = html.escape(slide.get("body", "") or "")

    title_size = _fit(title, [(26, 104), (48, 84), (72, 68), (100, 56), (999, 46)])
    if cover:
        title_size = int(title_size * 1.1)

    # A photo needs heavy cover or the title is unreadable; our own texture is
    # already dark and covering it would erase it.
    scrim = (
        "rgba(14,14,16,.20) 0%, rgba(14,14,16,.45) 55%, rgba(14,14,16,.82) 100%"
        if soft_background else
        "rgba(14,14,16,.55) 0%, rgba(14,14,16,.78) 46%, rgba(14,14,16,.96) 100%"
    )
    bg_layer = ""
    if background and background.exists():
        bg_layer = f"""
    <div class="bg" style="background-image:url('{_data_uri(background)}')"></div>
    <div class="scrim"></div>"""

    dots = "".join(
        f'<i class="{"on" if i == index else ""}"></i>' for i in range(1, total + 1)
    ) if total > 1 else ""

    return f"""<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{w}px; height:{h}px; overflow:hidden; }}
  body {{
    background:{p['bg']}; color:{p['fg']};
    font-family:{f['display']};
    -webkit-font-smoothing:antialiased;
    display:flex; flex-direction:column;
    padding:{'96px 88px 84px' if h < 1500 else '150px 88px 120px'};
    position:relative;
  }}
  .bg {{ position:absolute; inset:0; background-size:cover; background-position:center;
        filter:saturate(.72) contrast(1.05); }}
  .scrim {{ position:absolute; inset:0;
        background:linear-gradient(180deg, {scrim}); }}
  .frame {{ position:absolute; inset:34px; border:1px solid {p['line']};
        border-radius:22px; pointer-events:none; }}
  .inner {{ position:relative; z-index:2; display:flex; flex-direction:column;
        height:100%; }}
  .kicker {{
    font-family:{f['mono']}; font-size:26px; letter-spacing:.20em;
    text-transform:uppercase; color:{p['accent']};
    display:flex; align-items:center; gap:20px;
  }}
  .kicker::after {{ content:""; flex:1; height:1px; background:{p['line']}; }}
  .stack {{ flex:1; display:flex; flex-direction:column; justify-content:center;
        padding:56px 0; }}
  h1 {{
    font-size:{title_size}px; line-height:1.06; font-weight:700;
    letter-spacing:-.028em; text-wrap:balance;
  }}
  .body {{
    margin-top:38px; font-size:34px; line-height:1.45; color:{p['muted']};
    max-width:22ch; text-wrap:pretty;
  }}
  .rule {{ width:120px; height:5px; background:{p['accent']}; border-radius:3px;
        margin-top:44px; }}
  footer {{
    position:relative; z-index:2; display:flex; align-items:center;
    justify-content:space-between;
    font-family:{f['mono']}; font-size:24px; color:{p['muted']};
    letter-spacing:.06em;
  }}
  .dots {{ display:flex; gap:9px; }}
  .dots i {{ width:9px; height:9px; border-radius:50%; background:{p['line']};
        display:block; }}
  .dots i.on {{ background:{p['accent']}; }}
</style>
{bg_layer}
<div class="frame"></div>
<div class="inner">
  {f'<div class="kicker">{kicker}</div>' if kicker else ''}
  <div class="stack">
    <h1>{title}</h1>
    {f'<div class="body">{body}</div>' if body else ''}
    {'<div class="rule"></div>' if cover else ''}
  </div>
</div>
<footer>
  <span>{html.escape(b['handle'])}</span>
  <span class="dots">{dots}</span>
</footer>"""


# No --user-data-dir: with a fresh profile headless Chrome starts its
# first-run routine and hangs. The default profile works, even with Chrome
# already open.
QUIET_FLAGS = [
    "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    "--disable-translate", "--mute-audio", "--no-pings",
]


def _shoot(chrome: str, html_text: str, out: Path, size: tuple[int, int]) -> None:
    w, h = size
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "slide.html"
        src.write_text(html_text)
        cmd = [
            chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", "--virtual-time-budget=2000",
            *QUIET_FLAGS,
            f"--window-size={w},{h}", f"--screenshot={out}", str(src),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            raise RenderError(f"Chrome did not respond while rendering {out.name}.")
    if not out.exists() or out.stat().st_size == 0:
        raise RenderError(f"Chrome did not produce {out.name}: {proc.stderr[-400:]}")


def render(post: dict, b: dict | None = None) -> list[Path]:
    b = b or brand.load()
    slides = post.get("slides") or []
    if not slides:
        raise RenderError("No slides to render: run `igforge write` first.")

    chrome = find_chrome()
    size = SIZES.get(post.get("format", "carousel"), SIZES["carousel"])
    outdir = store.post_dir(post["id"]) / "slides"
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)

    hero = store.post_dir(post["id"]) / "hero.png"
    soft = post.get("hero_provider") == "texture"
    made = []
    for i, slide in enumerate(slides, 1):
        out = outdir / f"{i:02d}.png"
        _shoot(
            chrome,
            slide_html(slide, index=i, total=len(slides), b=b, size=size,
                       background=hero if (i == 1 and hero.exists()) else None,
                       soft_background=soft),
            out, size,
        )
        made.append(out)

    post.setdefault("assets", {})["slides"] = [str(p) for p in made]
    if post.get("status") == "draft":
        post["status"] = "ready"
    store.save_post(post)
    return made


def texture(post: dict, b: dict | None = None) -> Path:
    """Procedural cover, for when no image generator is reachable.

    Deterministic on the post id: two different posts don't look alike, the
    same post redone tomorrow is identical.
    """
    b = b or brand.load()
    p = b["palette"]
    seed = int(hashlib.sha256(post["id"].encode()).hexdigest()[:8], 16)

    def pick(n: int, lo: int, hi: int) -> int:
        return lo + (seed >> (n * 5)) % max(1, hi - lo)

    # Radial gradients instead of blurred divs: the blur, clipped by the page
    # edge, left a hard rectangle in the corners.
    alphas = (0.30, 0.16, 0.22)
    glows = ", ".join(
        f"radial-gradient({pick(i, 45, 85)}% {pick(i + 1, 40, 75)}% "
        f"at {pick(i + 2, 8, 92)}% {pick(i + 3, 10, 90)}%, "
        f"{_rgba([p['accent'], p['fg'], p['muted']][i % 3], alphas[i % 3])} 0%, "
        f"{_rgba([p['accent'], p['fg'], p['muted']][i % 3], 0)} 70%)"
        for i in range(4)
    )

    html_text = f"""<meta charset="utf-8"><style>
      html,body {{ margin:0; width:1080px; height:1350px; overflow:hidden; }}
      body {{ background:{glows}, {p['bg']}; position:relative; }}
      /* screen + grayscale: on a dark background an overlay would be invisible.
         Explicit width/height: an <svg> with no size falls back to the default
         300x150 and leaves a hard rectangle in the top-left corner. */
      .grain {{ position:absolute; inset:0; width:100%; height:100%;
                opacity:.13; mix-blend-mode:screen;
                filter:grayscale(1) contrast(1.5); }}
    </style>
    <svg class="grain" xmlns="http://www.w3.org/2000/svg">
      <filter id="n"><feTurbulence type="fractalNoise" baseFrequency="{0.6 + (seed % 40) / 100:.2f}"
        numOctaves="3" stitchTiles="stitch"/></filter>
      <rect width="100%" height="100%" filter="url(#n)"/>
    </svg>"""

    out = store.post_dir(post["id"]) / "hero.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    _shoot(find_chrome(), html_text, out, (1080, 1350))
    return out


def contact_sheet(post: dict) -> Path | None:
    """A preview strip of the slides, handy for an at-a-glance check."""
    paths = [Path(p) for p in post.get("assets", {}).get("slides", [])]
    paths = [p for p in paths if p.exists()]
    if not paths:
        return None
    imgs = "".join(
        f'<img src="{_data_uri(p)}">' for p in paths
    )
    b = brand.load()
    html_text = f"""<meta charset="utf-8"><style>
      body {{ margin:0; background:{b['palette']['bg']}; display:flex; gap:24px;
             padding:24px; }}
      img {{ height:520px; border-radius:12px; display:block; }}
    </style>{imgs}"""
    out = store.post_dir(post["id"]) / "preview.png"
    width = min(24 + len(paths) * (520 * 1080 // 1350 + 24), 8000)
    _shoot(find_chrome(), html_text, out, (width, 568))
    return out
