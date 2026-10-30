"""The brain: headless `claude -p`.

No API key to manage — it uses the Claude Code login already on the machine.
Two modes: `ask` for pure text/JSON (no tools, neutral cwd) and `agent` for
jobs that have to touch the world (Higgsfield MCP, curl).
"""

import json
import re
import subprocess
import tempfile

MODEL_WRITE = "claude-opus-5"
MODEL_QUICK = "claude-sonnet-5"

# Pure writing needs nothing: strip the tools so it doesn't wander off reading
# things instead of writing.
_NO_TOOLS = [
    "--disallowed-tools", "Bash", "Write", "Edit", "NotebookEdit",
    "Task", "WebFetch", "WebSearch", "Read", "Glob", "Grep",
]


class BrainError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int) -> str:
    with tempfile.TemporaryDirectory() as neutral_cwd:
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=neutral_cwd
            )
        except subprocess.TimeoutExpired:
            raise BrainError(f"the brain did not answer within {timeout}s")
    if proc.returncode != 0:
        raise BrainError((proc.stderr or proc.stdout or "unknown error").strip()[:800])
    return proc.stdout.strip()


def ask(prompt: str, *, system: str = "", model: str = MODEL_WRITE, timeout: int = 420) -> str:
    cmd = ["claude", "-p", prompt, "--model", model, *_NO_TOOLS]
    if system:
        cmd += ["--append-system-prompt", system]
    return _run(cmd, timeout)


def ask_json(prompt: str, *, system: str = "", model: str = MODEL_WRITE,
             timeout: int = 420, retries: int = 2):
    """Like `ask`, but demands JSON. If the model rambles, send it back."""
    hint = (
        "\n\nReply ONLY with valid JSON: no text before or after, "
        "no comments, no markdown code block."
    )
    last = ""
    for attempt in range(retries + 1):
        raw = ask(prompt + hint, system=system, model=model, timeout=timeout)
        last = raw
        try:
            return _extract_json(raw)
        except ValueError:
            prompt = (
                f"{prompt}\n\nThe previous attempt was not valid JSON. "
                f"Here is what you replied:\n{raw[:1500]}\nTry again, JSON only."
            )
    raise BrainError(f"no valid JSON after {retries + 1} attempts:\n{last[:600]}")


def _extract_json(raw: str):
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Last resort: the first balanced object/array in the text. Whoever opens
    # first wins: an array of objects must not collapse into its first
    # element.
    candidates = [(raw.find(o), o, c) for o, c in (("{", "}"), ("[", "]"))]
    for start, opener, closer in sorted(c for c in candidates if c[0] >= 0):
        if start < 0:
            continue
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(raw[start:], start):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError("no JSON in the text")


def agent(prompt: str, *, tools: list[str], cwd: str, model: str = MODEL_QUICK,
          timeout: int = 900) -> str:
    """Work that touches the world: MCP, downloads, files. Permissions pre-granted."""
    cmd = [
        "claude", "-p", prompt, "--model", model,
        "--allowed-tools", *tools,
        "--permission-mode", "bypassPermissions",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except subprocess.TimeoutExpired:
        raise BrainError(f"the agent did not finish within {timeout}s")
    if proc.returncode != 0:
        raise BrainError((proc.stderr or proc.stdout or "unknown error").strip()[:800])
    return proc.stdout.strip()
