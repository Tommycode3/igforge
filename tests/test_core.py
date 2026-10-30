"""Tests for the deterministic parts: no brain, no network.

    python3 -m unittest discover -s tests -t .
"""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["IGFORGE_HOME"] = _TMP.name

from igforge import brain, brand, compose, mine, plan, publish, render, store  # noqa: E402


class TestStore(unittest.TestCase):
    def setUp(self):
        store.init_dirs()

    def test_slug_strips_accents_and_punctuation(self):
        self.assertEqual(store.slugify("Why the café bring-up failed!"),
                         "why-the-cafe-bring-up-failed")

    def test_slug_never_empty(self):
        self.assertEqual(store.slugify("🙂🙂"), "post")

    def test_new_id_is_unique(self):
        a = store.new_id("same title")
        store.post_dir(a).mkdir(parents=True)
        b = store.new_id("same title")
        self.assertNotEqual(a, b)

    def test_resolve_by_prefix(self):
        post = {"id": store.new_id("a test post"), "status": "idea", "hook": "x"}
        store.save_post(post)
        self.assertEqual(store.resolve("a-test-post")["id"], post["id"])

    def test_resolve_unknown_raises(self):
        with self.assertRaises(SystemExit):
            store.resolve("does-not-exist-at-all")

    def test_roundtrip(self):
        post = {"id": store.new_id("roundtrip"), "status": "draft", "hook": "hello"}
        store.save_post(post)
        self.assertEqual(store.load_post(post["id"])["hook"], "hello")
        store.delete_post(post["id"])
        self.assertIsNone(store.load_post(post["id"]))


class TestBrand(unittest.TestCase):
    def test_prompt_contains_the_essentials(self):
        text = brand.as_prompt(brand.load())
        self.assertIn("AUTHOR PROFILE", text)
        self.assertIn("NEVER DO", text)
        self.assertIn("Content language: en", text)

    def test_missing_keys_fall_back_to_default(self):
        brand.save({"handle": "@other"})
        b = brand.load()
        self.assertEqual(b["handle"], "@other")
        self.assertIn("palette", b)
        brand.save(brand.DEFAULT)


class TestJsonExtraction(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(brain._extract_json('{"a": 1}'), {"a": 1})

    def test_fenced(self):
        self.assertEqual(brain._extract_json('```json\n[{"a": 1}]\n```'), [{"a": 1}])

    def test_with_chatter_around(self):
        raw = 'Sure, here you go:\n[{"hook": "hello"}]\nHope that works.'
        self.assertEqual(brain._extract_json(raw), [{"hook": "hello"}])

    def test_braces_inside_strings_dont_confuse_it(self):
        raw = 'here {"caption": "use } and { like this", "n": 2} done'
        self.assertEqual(brain._extract_json(raw)["n"], 2)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            brain._extract_json("no json here")


class TestMine(unittest.TestCase):
    def test_finds_repo_and_skips_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "project"
            repo.mkdir()
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
            run = lambda *a: subprocess.run(a, cwd=repo, env=env, capture_output=True)
            run("git", "init", "-q")
            (repo / "f.txt").write_text("one")
            run("git", "add", "-A")
            run("git", "commit", "-qm", "Added the 50 Hz notch filter")
            (repo / "f.txt").write_text("two")
            run("git", "add", "-A")
            run("git", "commit", "-qm", "wip")

            material = mine.harvest([str(tmp)], days=30)
            subjects = [c["subject"] for c in material["commits"]]
            self.assertIn("Added the 50 Hz notch filter", subjects)
            self.assertNotIn("wip", subjects)
            # the shortstat must land on the right commit, not the next one
            real = next(c for c in material["commits"] if c["subject"].startswith("Added"))
            self.assertIn("file changed", real["stat"])

    def test_prompt_survives_empty_material(self):
        text = mine.as_prompt({"days": 7, "commits": [], "notes": []})
        self.assertIn("no commits", text)


class TestPlan(unittest.TestCase):
    def setUp(self):
        for p in store.all_posts():
            store.delete_post(p["id"])

    def _post(self, title, strength):
        post = {"id": store.new_id(title), "status": "ready", "hook": title,
                "strength": strength, "format": "carousel"}
        store.save_post(post)
        return post

    def test_strongest_gets_the_earliest_slot(self):
        weak, strong = self._post("weak", 3), self._post("strong", 9)
        plan.autoschedule([weak, strong])
        self.assertLess(store.load_post(strong["id"])["schedule"]["at"],
                        store.load_post(weak["id"])["schedule"]["at"])

    def test_slots_are_never_shared(self):
        posts = [self._post(f"post {i}", i) for i in range(5)]
        plan.autoschedule(posts)
        times = [store.load_post(p["id"])["schedule"]["at"] for p in posts]
        self.assertEqual(len(times), len(set(times)))

    def test_scheduled_slots_land_on_configured_days(self):
        posts = [self._post(f"p{i}", 1) for i in range(4)]
        plan.autoschedule(posts)
        weekdays = {d for d, _ in plan.DEFAULT_SLOTS}
        for p in posts:
            when = datetime.fromisoformat(store.load_post(p["id"])["schedule"]["at"])
            self.assertIn(when.weekday(), weekdays)
            self.assertGreater(when, datetime.now())

    def test_parse_dates(self):
        self.assertEqual(plan._parse("2026-08-12 19:30").hour, 19)
        self.assertEqual(plan._parse("2026-08-12").hour, 19)  # default time
        short = plan._parse("12/08 21:00")
        self.assertEqual((short.day, short.month, short.hour), (12, 8, 21))
        self.assertEqual(short.year, datetime.now().year)
        for word in ("today", "oggi", "tomorrow", "domani"):
            self.assertEqual(plan._parse(word).hour, 19, word)
        with self.assertRaises(SystemExit):
            plan._parse("next month")


class TestRenderHtml(unittest.TestCase):
    def test_escapes_user_text(self):
        html = render.slide_html(
            {"kicker": "A & B", "title": "<script>alert(1)</script>", "body": ""},
            index=1, total=3, b=brand.load(), size=(1080, 1350),
        )
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("A &amp; B", html)

    def test_long_titles_get_smaller_type(self):
        b, size = brand.load(), (1080, 1350)
        short = render.slide_html({"title": "Short"}, index=2, total=2, b=b, size=size)
        long = render.slide_html({"title": "x" * 120}, index=2, total=2, b=b, size=size)
        self.assertGreater(_font_px(short), _font_px(long))

    def test_dot_indicator_marks_current_slide(self):
        html = render.slide_html({"title": "t"}, index=2, total=4, b=brand.load(),
                                 size=(1080, 1350))
        self.assertEqual(html.count('<i class="on">'), 1)
        self.assertEqual(html.count("<i class="), 4)

    def test_single_slide_has_no_dots(self):
        html = render.slide_html({"title": "t"}, index=1, total=1, b=brand.load(),
                                 size=(1080, 1350))
        self.assertNotIn("<i class=", html)


def _font_px(html: str) -> int:
    import re
    return int(re.search(r"h1 \{\s*font-size:(\d+)px", html).group(1))


class TestComposeOutput(unittest.TestCase):
    def test_readable_files_are_written(self):
        post = {
            "id": store.new_id("readable"), "status": "draft", "format": "carousel",
            "hook": "The bring-up failed because of one footprint",
            "caption": "Line one.\n\nLine two.", "hashtags": ["#a", "#b"],
            "alt_text": "a circuit board", "slides": [{"kicker": "K", "title": "T", "body": "B"}],
            "reel_script": [],
        }
        store.save_post(post)
        compose._write_readable(post)
        d = store.post_dir(post["id"])
        self.assertEqual((d / "caption.txt").read_text().strip(),
                         "Line one.\n\nLine two.\n\n#a #b".strip())
        self.assertIn("## Slides", (d / "POST.md").read_text())


class TestFormatContract(unittest.TestCase):
    def test_single_keeps_one_slide_even_if_the_model_sends_more(self):
        slides = [{"title": f"t{i}"} for i in range(4)]
        self.assertEqual(len(compose._fit_slides(slides, "single")), 1)

    def test_carousel_is_capped_at_ten(self):
        slides = [{"title": f"t{i}"} for i in range(14)]
        self.assertEqual(len(compose._fit_slides(slides, "carousel")), 10)

    def test_slides_without_a_title_are_dropped(self):
        slides = [{"title": "good"}, {"kicker": "kicker only"}, "garbage"]
        self.assertEqual(compose._fit_slides(slides, "carousel"), [{"title": "good"}])

    def test_hook_follows_the_caption(self):
        post = {"caption": "\n  The real first line.\n\nSecond.", "hook": "old hook"}
        self.assertEqual(compose._hook_of(post), "The real first line.")


class TestPublish(unittest.TestCase):
    def test_caption_joins_hashtags_and_respects_the_limit(self):
        post = {"caption": "x" * 2300, "hashtags": ["#a"]}
        self.assertEqual(len(publish.full_caption(post)), 2200)

    def test_dry_run_reports_what_is_missing(self):
        post = {"id": store.new_id("dry"), "format": "carousel", "caption": "c",
                "hashtags": [], "assets": {"slides": []}}
        store.save_post(post)
        with self.assertRaises(publish.PublishError):
            publish.publish(post, dry_run=True)  # no images

    def test_reels_are_refused_with_a_clear_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "1.png"
            img.write_bytes(b"x")
            post = {"id": store.new_id("reel"), "format": "reel", "caption": "c",
                    "assets": {"slides": [str(img)]}}
            store.save_post(post)
            with self.assertRaisesRegex(publish.PublishError, "video"):
                publish.publish(post, dry_run=True)


class TestCli(unittest.TestCase):
    def test_help_works_for_every_subcommand(self):
        parser = __import__("igforge.__main__", fromlist=["build_parser"]).build_parser()
        for name, sub in parser._subparsers._group_actions[0].choices.items():
            self.assertTrue(sub.format_help(), name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
