"""igforge CLI."""

import argparse
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from . import __version__, brain, brand, compose, mine, plan, publish, render, store, visual

DIM, BOLD, GREEN, YELLOW, RED, RESET = (
    "\033[2m", "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
)
if not sys.stdout.isatty():
    DIM = BOLD = GREEN = YELLOW = RED = RESET = ""

STEP = f"{DIM}·{RESET}"


def say(msg: str) -> None:
    print(msg, flush=True)


def step(msg: str) -> None:
    print(f"{STEP} {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{YELLOW}!{RESET} {msg}", flush=True)


# ---------------------------------------------------------------- commands

def cmd_init(args):
    store.init_dirs()
    b = brand.ensure()
    ok(f"Data folder: {store.HOME}")
    ok(f"Brand kit: {brand.path()}")
    say("")
    say(f"The brand kit is {BOLD}the file that decides output quality{RESET}.")
    say("Open it and make it yours (persona, topics, tone, colors):")
    say(f"  {DIM}igforge brand --edit{RESET}")
    say("")
    say("Then the full run, on its own:")
    say(f"  {DIM}igforge auto{RESET}")


def cmd_brand(args):
    store.init_dirs()
    brand.ensure()
    if args.edit:
        subprocess.run(["open", "-t", str(brand.path())])
        return
    b = brand.load()
    say(brand.as_prompt(b))
    say(f"{DIM}file: {brand.path()}{RESET}")


def cmd_inbox(args):
    store.init_dirs()
    text = " ".join(args.text) if args.text else sys.stdin.read()
    text = text.strip()
    if not text:
        raise SystemExit("Nothing to save.")
    name = f"{datetime.now():%Y%m%d-%H%M%S}.md"
    (store.INBOX / name).write_text(text + "\n")
    ok(f"Added to inbox: {name}")
    say(f"{DIM}It will be used on the next `igforge mine`.{RESET}")


def cmd_mine(args):
    store.init_dirs()
    b = brand.ensure()
    days = args.days or b["sources"]["days"]
    step(f"Looking for commits and notes from the last {days} days…")
    material = mine.harvest(b["sources"]["repos"], days)
    mine.save(material)
    ok(f"{len(material['commits'])} commits from {material['repos_scanned']} repos, "
       f"{len(material['notes'])} notes")
    for repo, n in list(material["by_repo"].items())[:12]:
        say(f"  {DIM}{n:>3}{RESET}  {repo}")
    if args.show:
        say("")
        say(mine.as_prompt(material))


def _material_text(days: int | None = None) -> str:
    b = brand.load()
    material = mine.latest()
    if not material or days is not None:
        material = mine.harvest(b["sources"]["repos"], days or b["sources"]["days"])
        mine.save(material)
    return mine.as_prompt(material)


def cmd_ideas(args):
    store.init_dirs()
    brand.ensure()
    step("Gathering raw material…")
    material = _material_text(args.days)
    step(f"Asking the brain for {args.n} ideas… {DIM}(may take a minute){RESET}")
    ideas = compose.ideate(material, args.n)
    say("")
    for i, idea in enumerate(ideas, 1):
        strength = idea.get("strength", "?")
        say(f"{BOLD}{i}. {idea['hook']}{RESET}")
        say(f"   {DIM}{idea.get('format','')} · strength {strength}/10 · {idea.get('angle','')}{RESET}")
        say(f"   {DIM}why now: {idea.get('why_now','')}{RESET}")
        say("")
    if args.save:
        for idea in ideas:
            post = compose.save_idea(idea)
            ok(f"saved {post['id']}")
    else:
        say(f"{DIM}Add --save to turn them into drafts.{RESET}")


def cmd_new(args):
    store.init_dirs()
    brand.ensure()
    topic = " ".join(args.topic)
    post = compose.save_idea({
        "title": topic, "hook": topic, "angle": topic,
        "format": args.format, "why_now": "requested by hand", "source": "manual",
    })
    ok(f"created {post['id']}")
    if not args.bare:
        _build(post, hero=not args.no_hero, notes=args.notes or "")


def cmd_write(args):
    post = store.resolve(args.id)
    step("Writing…")
    post = compose.write(post, material=_material_text(), notes=args.notes or "")
    step("Running the editor…")
    post = compose.critique(post)
    ok(f"{store.post_dir(post['id']) / 'POST.md'}")
    _print_post(post)


def cmd_hero(args):
    post = store.resolve(args.id)
    step(f"Generating the cover with {args.provider}… {DIM}(can take 2-3 minutes){RESET}")
    path = visual.hero(post, provider=args.provider)
    ok(str(path))


def cmd_render(args):
    post = store.resolve(args.id)
    step("Rendering the slides…")
    made = render.render(post)
    ok(f"{len(made)} slides in {made[0].parent}")
    try:
        sheet = render.contact_sheet(post)
        if sheet:
            say(f"{DIM}preview: {sheet}{RESET}")
    except render.RenderError:
        pass


def _build(post: dict, *, hero: bool, notes: str = "") -> dict:
    step("Writing the copy…")
    post = compose.write(post, material=_material_text(), notes=notes)
    step("Running the editor…")
    post = compose.critique(post)
    if hero:
        try:
            step("Generating the cover…")
            visual.hero(post)
        except (visual.VisualError, brain.BrainError) as e:
            warn(f"cover skipped: {e}")
    step("Rendering the slides…")
    try:
        render.render(post)
        render.contact_sheet(post)
    except render.RenderError as e:
        warn(f"render skipped: {e}")
    post = store.load_post(post["id"])
    ok(f"ready: {store.post_dir(post['id'])}")
    return post


def cmd_build(args):
    post = store.resolve(args.id)
    post = _build(post, hero=not args.no_hero, notes=args.notes or "")
    _print_post(post)


def cmd_auto(args):
    store.init_dirs()
    brand.ensure()
    say(f"{BOLD}igforge auto{RESET} {DIM}— {args.n} posts, from zero to ready{RESET}")
    say("")
    step("Gathering what you did…")
    material = _material_text(args.days)
    step(f"Generating ideas…")
    ideas = compose.ideate(material, args.n)
    if not ideas:
        raise SystemExit("No ideas produced. Check that there is material: `igforge mine --show`.")

    built = []
    for i, idea in enumerate(ideas, 1):
        say("")
        say(f"{BOLD}[{i}/{len(ideas)}]{RESET} {idea['hook']}")
        post = compose.save_idea(idea)
        try:
            built.append(_build(post, hero=not args.no_hero))
        except (brain.BrainError, render.RenderError) as e:
            warn(f"skipped {post['id']}: {e}")

    if built and not args.no_schedule:
        say("")
        step("Scheduling…")
        plan.autoschedule(built)
        say("")
        say(plan.render_calendar())

    say("")
    ok(f"{len(built)} posts ready in {store.POSTS}")
    if built:
        say(f"{DIM}igforge open {built[0]['id']}{RESET}")


def cmd_list(args):
    posts = store.all_posts()
    if args.status:
        posts = [p for p in posts if p.get("status") == args.status]
    if not posts:
        say("No posts. `igforge auto` to get started.")
        return
    posts.sort(key=lambda p: p.get("schedule", {}).get("at") or p.get("created_at", ""))
    for p in posts:
        when = p.get("schedule", {}).get("at", "")
        mark = {"published": f"{GREEN}✓{RESET}", "scheduled": "·", "ready": "·",
                "draft": f"{YELLOW}~{RESET}", "idea": "○"}.get(p.get("status"), " ")
        slides = len(p.get("assets", {}).get("slides", []))
        say(f"{mark} {p['id']}")
        say(f"    {DIM}{p.get('format',''):<8} {when:<16} {slides} slides{RESET}  {p.get('hook','')[:60]}")


def _print_post(post: dict) -> None:
    say("")
    say(f"{BOLD}{post.get('hook','')}{RESET}")
    say("")
    say(textwrap.indent(post.get("caption", ""), "  "))
    say("")
    say(f"  {DIM}{' '.join(post.get('hashtags', []))}{RESET}")
    if post.get("edit", {}).get("verdict"):
        say("")
        say(f"  {DIM}editor: {post['edit']['verdict']}{RESET}")


def cmd_show(args):
    post = store.resolve(args.id)
    _print_post(post)
    say("")
    for i, s in enumerate(post.get("slides", []), 1):
        say(f"  {i}. [{s.get('kicker','')}] {BOLD}{s.get('title','')}{RESET}")
        if s.get("body"):
            say(f"     {DIM}{s['body']}{RESET}")
    for beat in post.get("reel_script", []):
        say(f"  {DIM}{beat.get('t','')}{RESET} {beat.get('visual','')} — {beat.get('vo','')}")
    say("")
    say(f"  {DIM}{store.post_dir(post['id'])}{RESET}")


def cmd_open(args):
    post = store.resolve(args.id)
    subprocess.run(["open", str(store.post_dir(post["id"]))])
    preview = store.post_dir(post["id"]) / "preview.png"
    if preview.exists():
        subprocess.run(["open", str(preview)])


def cmd_calendar(args):
    say(plan.render_calendar(args.limit))


def cmd_schedule(args):
    post = store.resolve(args.id)
    plan.schedule_one(post, args.when)
    ok(f"{post['id']} → {post['schedule']['at']}")


def cmd_due(args):
    posts = plan.due()
    if not posts:
        say("Nothing to publish right now.")
        return
    for p in posts:
        say(f"{p['schedule']['at']}  {p['id']}  {p.get('hook','')[:60]}")


def cmd_publish(args):
    post = store.resolve(args.id)
    dry = not args.now
    result = publish.publish(post, dry_run=dry)
    if result.get("dry_run"):
        say(f"{BOLD}Dry run{RESET} — nothing was published.")
        say("")
        say("Images, in order:")
        for p in result["images"]:
            say(f"  {p}")
        say("")
        say("Caption (hashtags included):")
        say(textwrap.indent(result["caption"], "  "))
        if result["missing_config"]:
            say("")
            warn("To actually publish you need: " + ", ".join(result["missing_config"]))
            say(f"{DIM}Put them in {store.HOME / 'config.json'} or in environment variables.{RESET}")
        else:
            say("")
            say(f"{DIM}All configured: `igforge publish {args.id} --now`{RESET}")
    else:
        ok(f"published: media_id {result.get('media_id')}")


def cmd_export(args):
    post = store.resolve(args.id)
    dest = Path(args.to).expanduser() if args.to else Path.home() / "Desktop" / f"IG-{post['id']}"
    dest.mkdir(parents=True, exist_ok=True)
    src = store.post_dir(post["id"])
    for f in sorted((src / "slides").glob("*.png")) if (src / "slides").exists() else []:
        (dest / f.name).write_bytes(f.read_bytes())
    (dest / "caption.txt").write_text(publish.full_caption(post) + "\n")
    ok(f"exported to {dest}")
    subprocess.run(["open", str(dest)])


def cmd_rm(args):
    post = store.resolve(args.id)
    store.delete_post(post["id"])
    ok(f"deleted {post['id']}")


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="igforge",
        description="From raw material to a ready-to-post Instagram post.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            typical run
              igforge init                    first time: creates the brand kit
              igforge brand --edit            make it yours (matters most)
              igforge auto                    ideas + copy + slides + calendar
              igforge open <id>               look at the result
              igforge publish <id>            dry run, or --now if configured
        """),
    )
    p.add_argument("--version", action="version", version=f"igforge {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create folders and brand kit").set_defaults(fn=cmd_init)

    s = sub.add_parser("brand", help="show or edit the brand kit")
    s.add_argument("--edit", action="store_true", help="open it in the editor")
    s.set_defaults(fn=cmd_brand)

    s = sub.add_parser("inbox", help="jot down a quick idea")
    s.add_argument("text", nargs="*")
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("mine", help="collect commits and notes")
    s.add_argument("--days", type=int)
    s.add_argument("--show", action="store_true", help="print the raw material")
    s.set_defaults(fn=cmd_mine)

    s = sub.add_parser("ideas", help="propose post ideas")
    s.add_argument("-n", type=int, default=6)
    s.add_argument("--days", type=int)
    s.add_argument("--save", action="store_true", help="save them as drafts")
    s.set_defaults(fn=cmd_ideas)

    s = sub.add_parser("new", help="create a post from your own topic")
    s.add_argument("topic", nargs="+")
    s.add_argument("--format", choices=["carousel", "single", "reel"], default="carousel")
    s.add_argument("--notes", help="directions for the writer")
    s.add_argument("--no-hero", action="store_true")
    s.add_argument("--bare", action="store_true", help="create the idea only, don't build")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("write", help="write a post's copy")
    s.add_argument("id")
    s.add_argument("--notes")
    s.set_defaults(fn=cmd_write)

    s = sub.add_parser("hero", help="generate the cover image")
    s.add_argument("id")
    s.add_argument("--provider", default="auto",
                   choices=["auto", "higgsfield", "huggingface", "texture"],
                   help="auto: try the AI generators, then fall back to the texture")
    s.set_defaults(fn=cmd_hero)

    s = sub.add_parser("render", help="render the PNG slides")
    s.add_argument("id")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("build", help="copy + cover + slides")
    s.add_argument("id")
    s.add_argument("--notes")
    s.add_argument("--no-hero", action="store_true")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("auto", help="all on its own: ideas → ready posts → calendar")
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--days", type=int)
    s.add_argument("--no-hero", action="store_true")
    s.add_argument("--no-schedule", action="store_true")
    s.set_defaults(fn=cmd_auto)

    s = sub.add_parser("list", help="list posts")
    s.add_argument("--status", choices=list(store.STATUSES))
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="show a post")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("open", help="open the post folder")
    s.add_argument("id")
    s.set_defaults(fn=cmd_open)

    s = sub.add_parser("calendar", help="the editorial calendar")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_calendar)

    s = sub.add_parser("schedule", help="pin a post to a date")
    s.add_argument("id")
    s.add_argument("when", help="2026-08-12 19:30 · 12/08 (day/month) · today · tomorrow")
    s.set_defaults(fn=cmd_schedule)

    sub.add_parser("due", help="what should be published now").set_defaults(fn=cmd_due)

    s = sub.add_parser("publish", help="publish (dry run by default)")
    s.add_argument("id")
    s.add_argument("--now", action="store_true", help="actually publish")
    s.set_defaults(fn=cmd_publish)

    s = sub.add_parser("export", help="folder ready to post by hand")
    s.add_argument("id")
    s.add_argument("--to")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("rm", help="delete a post")
    s.add_argument("id")
    s.set_defaults(fn=cmd_rm)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except (brain.BrainError, render.RenderError, visual.VisualError,
            publish.PublishError) as e:
        print(f"{RED}✗{RESET} {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
