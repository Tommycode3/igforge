"""Paths, ids and persistence. Everything on disk, everything readable by hand."""

import json
import os
import re
import shutil
import unicodedata
from datetime import date, datetime
from pathlib import Path

HOME = Path(os.environ.get("IGFORGE_HOME", Path.home() / ".igforge"))
POSTS = HOME / "posts"
INBOX = HOME / "inbox"
MATERIAL = HOME / "material"

STATUSES = ("idea", "draft", "ready", "scheduled", "published")


def init_dirs() -> None:
    for d in (HOME, POSTS, INBOX, MATERIAL):
        d.mkdir(parents=True, exist_ok=True)


def slugify(text: str, limit: int = 42) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:limit].rstrip("-")) or "post"


def new_id(title: str, when: date | None = None) -> str:
    day = (when or date.today()).isoformat()
    base = f"{day}-{slugify(title)}"
    candidate, n = base, 2
    while (POSTS / candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def post_dir(post_id: str) -> Path:
    return POSTS / post_id


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_post(post_id: str) -> dict | None:
    return read_json(post_dir(post_id) / "post.json")


def save_post(post: dict) -> Path:
    post["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = post_dir(post["id"]) / "post.json"
    write_json(path, post)
    return path


def all_posts() -> list[dict]:
    if not POSTS.exists():
        return []
    posts = [load_post(p.name) for p in sorted(POSTS.iterdir()) if p.is_dir()]
    return [p for p in posts if p]


def resolve(prefix: str) -> dict:
    """Accepts a partial id: `igforge show 08-07` is enough if it isn't ambiguous."""
    posts = all_posts()
    exact = [p for p in posts if p["id"] == prefix]
    if exact:
        return exact[0]
    hits = [p for p in posts if prefix in p["id"]]
    if not hits:
        raise SystemExit(f"No post matches {prefix!r}. Try `igforge list`.")
    if len(hits) > 1:
        ids = "\n  ".join(p["id"] for p in hits)
        raise SystemExit(f"{prefix!r} is ambiguous:\n  {ids}")
    return hits[0]


def delete_post(post_id: str) -> None:
    shutil.rmtree(post_dir(post_id), ignore_errors=True)
