"""Publishing to Instagram, optional.

Instagram only accepts public URLs, so the flow is: upload the PNGs to Vercel
Blob → create the containers → publish. You need a Business/Creator account
linked to a Facebook Page and a token with `instagram_content_publish`.

Without credentials the command stays a dry run that prepares the folder for
you to post by hand: that is the default, and it is already useful.
"""

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import store

GRAPH = "https://graph.facebook.com"
BLOB = "https://blob.vercel-storage.com"


class PublishError(RuntimeError):
    pass


def config() -> dict:
    import os
    cfg = store.read_json(store.HOME / "config.json", {}) or {}
    env = {
        "ig_user_id": os.environ.get("IG_USER_ID"),
        "ig_access_token": os.environ.get("IG_ACCESS_TOKEN"),
        "blob_token": os.environ.get("BLOB_READ_WRITE_TOKEN"),
    }
    cfg.update({k: v for k, v in env.items() if v})
    cfg.setdefault("graph_version", "v21.0")
    cfg.setdefault("blob_api_version", "7")
    return cfg


def configured(cfg: dict | None = None) -> bool:
    cfg = cfg or config()
    return bool(cfg.get("ig_user_id") and cfg.get("ig_access_token") and cfg.get("blob_token"))


def _request(url: str, *, method="GET", data=None, headers=None, timeout=120):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:600]
        raise PublishError(f"HTTP {e.code} on {urllib.parse.urlparse(url).path}: {detail}")
    except urllib.error.URLError as e:
        raise PublishError(f"network unreachable: {e.reason}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def upload(path: Path, cfg: dict) -> str:
    """Upload to Vercel Blob and return the public URL."""
    key = f"igforge/{path.parent.parent.name}/{path.name}"
    ctype = mimetypes.guess_type(path.name)[0] or "image/png"
    out = _request(
        f"{BLOB}/{urllib.parse.quote(key)}",
        method="PUT",
        data=path.read_bytes(),
        headers={
            "Authorization": f"Bearer {cfg['blob_token']}",
            "x-api-version": str(cfg["blob_api_version"]),
            "x-content-type": ctype,
            "x-add-random-suffix": "1",
            "Content-Type": ctype,
        },
        timeout=180,
    )
    url = out.get("url") or out.get("downloadUrl")
    if not url:
        raise PublishError(f"Vercel Blob did not return a URL: {str(out)[:300]}")
    return url


def _graph(cfg: dict, path: str, params: dict, method="POST") -> dict:
    params = {**params, "access_token": cfg["ig_access_token"]}
    url = f"{GRAPH}/{cfg['graph_version']}/{path}"
    if method == "GET":
        return _request(f"{url}?{urllib.parse.urlencode(params)}", method="GET")
    return _request(url, method="POST",
                    data=urllib.parse.urlencode(params).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"})


def _await_container(cfg: dict, container_id: str, tries: int = 30) -> None:
    for _ in range(tries):
        status = _graph(cfg, container_id, {"fields": "status_code,status"}, method="GET")
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"container {container_id} in state {code}: {status.get('status')}")
        time.sleep(4)
    raise PublishError(f"container {container_id} not ready after {tries * 4}s")


def full_caption(post: dict) -> str:
    tags = " ".join(post.get("hashtags", []))
    return (post.get("caption", "").rstrip() + ("\n\n" + tags if tags else ""))[:2200]


def publish(post: dict, *, dry_run: bool = True) -> dict:
    images = [Path(p) for p in post.get("assets", {}).get("slides", [])]
    images = [p for p in images if p.exists()]
    if not images:
        raise PublishError("No rendered images: run `igforge render` first.")
    if post.get("format") == "reel":
        raise PublishError(
            "Reels need a video: igforge only produces the script and the "
            "cover. Edit the video and upload it by hand."
        )

    cfg = config()
    if dry_run or not configured(cfg):
        missing = [k for k in ("ig_user_id", "ig_access_token", "blob_token") if not cfg.get(k)]
        return {
            "dry_run": True,
            "images": [str(p) for p in images],
            "caption": full_caption(post),
            "missing_config": missing,
        }

    urls = [upload(p, cfg) for p in images]
    ig = cfg["ig_user_id"]

    if len(urls) == 1:
        container = _graph(cfg, f"{ig}/media", {
            "image_url": urls[0], "caption": full_caption(post),
            "alt_text": post.get("alt_text", "")[:1000],
        })["id"]
    else:
        children = [
            _graph(cfg, f"{ig}/media", {"image_url": u, "is_carousel_item": "true"})["id"]
            for u in urls
        ]
        for child in children:
            _await_container(cfg, child)
        container = _graph(cfg, f"{ig}/media", {
            "media_type": "CAROUSEL", "children": ",".join(children),
            "caption": full_caption(post),
        })["id"]

    _await_container(cfg, container)
    result = _graph(cfg, f"{ig}/media_publish", {"creation_id": container})

    post["status"] = "published"
    post["published"] = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "media_id": result.get("id"),
        "urls": urls,
    }
    store.save_post(post)
    return post["published"]
