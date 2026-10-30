# igforge

igforge turns the commit history of your repositories into Instagram posts. It reads
`git log` and a folder of quick notes, proposes ideas, writes captions and slides,
runs an editor pass that strips numbers not found in the commits, renders the slides
to PNG, schedules them and, if configured, publishes through the Instagram Graph API.
Python 3.11+, standard library only. Text is written by `claude -p` (headless
[Claude Code](https://docs.anthropic.com/en/docs/claude-code)) with whatever login
Claude Code already has, so there is no API key to manage.

## Install

```sh
./scripts/install.sh              # creates ~/bin/igforge pointing at this checkout
./scripts/install.sh --weekly     # plus a launchd job: Mondays 08:00, prepares 3 posts
./scripts/uninstall.sh
```

Needs `~/bin` on your `PATH`, Claude Code (`claude`) logged in, and Google Chrome or
another Chromium.

## Usage

```sh
igforge auto                        # ideas, copy, slides, calendar, unattended
igforge auto -n 5 --days 30         # five posts, looking at the last month
igforge ideas -n 8                  # ideas only, you pick
igforge new "why I chose this ADC" --format carousel
igforge inbox "the footprint mistake would make a good post"
igforge calendar                    # what goes out when
igforge schedule <id> "12/08 19:30"
igforge open <id>                   # open the folder (any unique part of the id)
igforge publish <id>                # dry run: shows what would be published
igforge publish <id> --now
igforge export <id>                 # copy to ~/Desktop/IG-<id>, ready to post by hand
```

`igforge init` writes `~/.igforge/brand.json` (edit with `igforge brand --edit`). It
is sent verbatim to the model on every generation and decides most of the output:
name and handle, persona, audience, topics, tone, things to never do, closing lines,
hashtags, palette, fonts, cover style, which directories to mine, and the content
language. [`brand.example.json`](brand.example.json) documents every field with
neutral placeholders (the same defaults as `igforge/brand.py`).

Everything lives in `~/.igforge` (or `IGFORGE_HOME`) as plain files: `brand.json`,
`config.json`, `inbox/`, `material/` (what was mined, by date) and one folder per
post under `posts/<id>/` with `post.json`, `POST.md`, `caption.txt`, `hero.png`,
`slides/01.png …` and `preview.png`.

## How it works

`mine._git_repos` walks each configured root to depth 2, skipping `node_modules`,
`Library`, `build` and dot-dirs, and stops descending once it finds a repo. It runs
`git log --since=N.days.ago --no-merges --shortstat` and frames each record with ASCII
separators (`\x1e` per record, `\x1f` per field) so the `--shortstat` line lands in the
right commit. Merge, WIP, typo and version-bump commits are dropped; at most 200
commits are kept and 90 are shown to the model.

Ideation, writing and the editor pass each call `claude -p` with all tools disallowed,
in an empty temp dir. `brain.ask_json` needs JSON back, so `_extract_json` tries the
whole text, then a fenced block, then the first balanced `{…}` or `[…]` (tracking
strings and escapes, and taking whichever bracket opens first so an array of objects
is not mistaken for its first element). On failure it sends the reply back and asks
again, up to two times. The cover comes from `claude -p` driving the Higgsfield or
HuggingFace MCP server, falling back to a procedural SVG texture.

Slides are HTML pages in the brand palette and fonts, screenshotted by headless Chrome
at 1080×1350 (1080×1920 for reels). Title size is a step function of text length, all
text is HTML-escaped, and a carousel has at most 10 slides.

Slots are fixed at Tuesday 19:30, Thursday 19:30 and Saturday 11:00
(`plan.DEFAULT_SLOTS`). With $t_1 < t_2 < \dots$ the free slots after now and the new
posts sorted by the strength $s \in [1, 10]$ the model gave them during ideation,
$\operatorname{slot}(p_{(k)}) = t_k$: the strongest idea goes out first and nothing
collides with the existing calendar. `igforge schedule` overrides it (`2026-08-12 19:30`,
`12/08` as day/month, `today`, `tomorrow`; a date alone defaults to 19:30).

`python3 -m unittest discover -s tests -t .` runs 32 tests on the deterministic
parts: ids and slugs, repo discovery, git-log parsing, JSON extraction, calendar slots
and date parsing, HTML escaping, caption limits. The model and network are never called.

## Publishing

Dry run is the default. Automatic publishing needs `~/.igforge/config.json` (or
`IG_USER_ID`, `IG_ACCESS_TOKEN`, `BLOB_READ_WRITE_TOKEN`):

```json
{
  "ig_user_id": "17841…",
  "ig_access_token": "EAA…",
  "blob_token": "vercel_blob_rw_…"
}
```

The Instagram account must be Business or Creator, linked to a Facebook Page, with a
Meta app that has `instagram_content_publish`; use a long-lived token, the short-lived
one expires in an hour. The Graph API only takes public image URLs, so PNGs go to
Vercel Blob first. Carousels are published as child containers, each polled until
ready, then a `CAROUSEL` container and `media_publish`. Reels are not published;
igforge only produces their script and cover.

## Limitations

- macOS-oriented: `sips` for images, `launchd` and `osascript` for the weekly job.
  The core pipeline is plain Python.
- Needs Claude Code installed and logged in; MCP covers also need those servers
  configured in Claude Code.
- Prompts are in English and ask for output in the brand's `language`; other
  languages have not been re-checked since the prompts were translated.
- Graph API pinned to `v21.0` (configurable in `config.json`).

## License

MIT. See [LICENSE](LICENSE).
