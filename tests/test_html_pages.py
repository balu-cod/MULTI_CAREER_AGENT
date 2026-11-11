"""Every page must parse: all inline <script>s share one global scope in the browser, so a duplicated `let`/`const`
across two scripts is a fatal SyntaxError that silently kills the whole app (this once broke the sign-in screen)."""
import pathlib, re, shutil, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HtmlPages(unittest.TestCase):
    def check(self, code):
        f = pathlib.Path(tempfile.mktemp(suffix=".js")); f.write_text(code, "utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        f.unlink(missing_ok=True)
        return r.stderr.strip()

    def test_all_pages_scripts_parse_together(self):
        pages = sorted(ROOT.glob("*.html"))
        self.assertTrue(pages)
        for page in pages:
            html = page.read_text("utf-8")
            scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
            err = self.check("\n;\n".join(scripts))
            self.assertEqual(err, "", f"{page.name}: {err[-400:]}")

    def test_external_script_tags_have_no_dead_inline_body(self):
        for page in sorted(ROOT.glob("*.html")):
            for m in re.finditer(r'<script\b[^>]*\bsrc="[^"]+"[^>]*>(.*?)</script>', page.read_text("utf-8"), re.S):
                self.assertEqual(m.group(1).strip(), "", f"{page.name}: inline code inside a <script src> is ignored by browsers")

    def test_js_auth_parses(self):
        self.assertEqual(self.check((ROOT / "js" / "auth.js").read_text("utf-8")), "")

    def test_pages_load_shared_auth_script(self):
        for page in sorted(ROOT.glob("*.html")):
            h = page.read_text("utf-8")
            if "view-signin" in h:
                self.assertIn("js/auth.js", h, page.name)



    def test_ui_structure_views_and_unique_ids(self):
        from collections import Counter
        html = (ROOT / "index.html").read_text("utf-8")
        ids = re.findall(r'\bid="([^"]+)"', html)
        dups = {k: v for k, v in Counter(ids).items() if v > 1}
        self.assertEqual(dups, {}, f"Duplicate DOM IDs in index.html: {dups}")
        views = [m.group(1)[5:] for m in re.finditer(r'<section[^>]*id="(view-[^"]+)"', html)]
        sidebar_tabs = set(re.findall(r'data-tab="([^"]+)"', html))
        for v in views:
            if v in ("signin", "single-agent"):
                continue
            self.assertIn(v, sidebar_tabs, f"View view-{v} is missing from sidebar navigation")
        for stage_num in range(1, 6):
            self.assertIn(f'data-pipeline-stage="{stage_num}"', html)


if __name__ == "__main__":
    unittest.main()
