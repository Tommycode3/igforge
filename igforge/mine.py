"""Raw material: what you actually did, and what you jotted down.

Build-in-public only works if it starts from facts. This collects them from the
commits of every repo and from the inbox, without asking anyone anything.
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

from . import store

NOISE = ("merge branch", "merge pull request", "wip", "bump version", "typo", "fixup!")

# The home dir is full of huge trees with no repos in them: walking into them
# costs minutes and memory for nothing.
SKIP_DIRS = {
    "node_modules", ".git", "venv", ".venv", "build", "dist", "__pycache__",
    "Library", "Applications", "Movies", "Music", "Pictures", "Public",
    "Downloads", "Documents", "Documenti", "target", "Pods", ".Trash",
}


def _git_repos(roots: list[str], max_depth: int = 2) -> list[Path]:
    """The repos under the given roots, never descending into a repo once found."""
    found: list[Path] = []
    seen: set[Path] = set()

    def keep(path: Path) -> None:
        real = path.resolve()
        if real not in seen:
            seen.add(real)
            found.append(path)

    for root in roots:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        for dirpath, dirnames, _ in os.walk(base):
            here = Path(dirpath)
            if (here / ".git").exists():
                keep(here)
                # No searching inside a found repo — unless the root itself is
                # a repo (it happens: a version-controlled home), in which case
                # keep going, or everything under it vanishes.
                if here != base:
                    dirnames[:] = []
                    continue
            if len(here.relative_to(base).parts) >= max_depth:
                dirnames[:] = []
                continue
            dirnames[:] = [
                d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
            ]
    return found


def _log(repo: Path, days: int) -> list[dict]:
    # \x1e opens each record and \x1f separates fields: that way --shortstat,
    # which git prints after the body, lands in the last field of the right commit.
    try:
        out = subprocess.run(
            ["git", "log", f"--since={days}.days.ago", "--no-merges",
             "--pretty=format:%x1e%H%x1f%at%x1f%s%x1f%b%x1f", "--shortstat"],
            cwd=repo, capture_output=True, text=True, timeout=25,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    if out.returncode != 0:
        return []
    commits = []
    for record in out.stdout.split("\x1e"):
        if not record.strip():
            continue
        parts = record.split("\x1f")
        if len(parts) < 3:
            continue
        subject = parts[2].strip()
        if not subject or any(subject.lower().startswith(n) for n in NOISE):
            continue
        try:
            when = datetime.fromtimestamp(int(parts[1].strip())).strftime("%Y-%m-%d")
        except ValueError:
            continue
        stat = parts[4] if len(parts) > 4 else ""
        commits.append({
            "repo": repo.name,
            "when": when,
            "subject": subject,
            "body": (parts[3].strip()[:400] if len(parts) > 3 else ""),
            "stat": " ".join(stat.split())[:120],
        })
    return commits


def read_inbox() -> list[dict]:
    """Notes you tossed in there. They get consumed but not deleted."""
    notes = []
    if not store.INBOX.exists():
        return notes
    for f in sorted(store.INBOX.iterdir()):
        if f.is_file() and f.suffix in (".txt", ".md", ""):
            text = f.read_text(errors="ignore").strip()
            if text:
                notes.append({"source": f.name, "text": text[:2000]})
    return notes


def harvest(roots: list[str], days: int) -> dict:
    repos = _git_repos(roots)
    commits = []
    for repo in repos:
        commits.extend(_log(repo, days))
    commits.sort(key=lambda c: c["when"], reverse=True)

    by_repo: dict[str, list[dict]] = {}
    for c in commits:
        by_repo.setdefault(c["repo"], []).append(c)

    return {
        "harvested_at": datetime.now().isoformat(timespec="seconds"),
        "days": days,
        "repos_scanned": len(repos),
        "commits": commits[:200],
        "by_repo": {k: len(v) for k, v in sorted(
            by_repo.items(), key=lambda kv: -len(kv[1]))},
        "notes": read_inbox(),
    }


def as_prompt(material: dict) -> str:
    """The raw material made readable for the brain."""
    lines = [f"ACTUAL ACTIVITY IN THE LAST {material['days']} DAYS"]
    if not material["commits"]:
        lines.append("(no commits in this period)")
    current = None
    for c in material["commits"][:90]:
        if c["repo"] != current:
            current = c["repo"]
            lines.append(f"\n[{current}]")
        stat = f"  ({c['stat']})" if c["stat"] else ""
        lines.append(f"  {c['when']} · {c['subject']}{stat}")
        if c["body"]:
            first = c["body"].splitlines()[0][:160]
            if first:
                lines.append(f"      {first}")

    if material["notes"]:
        lines.append("\nHANDWRITTEN NOTES (inbox)")
        for n in material["notes"]:
            lines.append(f"  [{n['source']}] {n['text'][:600]}")
    return "\n".join(lines)


def save(material: dict) -> Path:
    path = store.MATERIAL / f"{material['harvested_at'][:10]}.json"
    store.write_json(path, material)
    return path


def latest() -> dict | None:
    if not store.MATERIAL.exists():
        return None
    files = sorted(store.MATERIAL.glob("*.json"))
    return store.read_json(files[-1]) if files else None
