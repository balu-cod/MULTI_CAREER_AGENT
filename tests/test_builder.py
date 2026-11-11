import tempfile, unittest
from unittest import mock
from live import runtime, builder

GOOD = '''from live.runtime import LiveAgent, agent
import re
@agent
class X(LiveAgent):
    name = "good_agent"; needs = []
    def run(self, ctx): ctx["insights"]["x"] = re.sub("a", "b", "aaa")
'''


class BuilderTests(unittest.TestCase):
    def _run(self, code):
        runtime.discover()
        with mock.patch.dict(runtime.TOOLS, {"ask_llm": lambda *a, **k: code}), mock.patch.object(builder, "ROOT", __import__("pathlib").Path(tempfile.mkdtemp())):
            builder.new_agent("x")

    def test_allowlisted_code_is_saved(self): self._run(GOOD)

    def test_rejects_unlisted_import(self):
        for bad in ("import os\n" + GOOD, "import subprocess\n" + GOOD, "from pathlib import Path\n" + GOOD):
            with self.assertRaises(SystemExit): self._run(bad)

    def test_rejects_dunder_and_dynamic_exec(self):
        with self.assertRaises(SystemExit): self._run(GOOD + "\nx = ().__class__.__bases__\n")
        with self.assertRaises(SystemExit): self._run(GOOD + "\nopen('f','w')\n")
        with self.assertRaises(SystemExit): self._run(GOOD + "\ngetattr(re, 'x')\n")
