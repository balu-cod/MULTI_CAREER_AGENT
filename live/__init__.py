"""Career Agent System: live layer (single source of truth for the version)."""
import importlib.abc, importlib.util, pathlib, sys

_HERE = pathlib.Path(__file__).resolve().parent

class _LiveFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("live."):
            return None
        subname = fullname.split(".", 1)[1]
        mod = _HERE / f"{subname}.py"
        if mod.is_file():
            return importlib.util.spec_from_file_location(fullname, mod)
        return None

if not any(isinstance(f, _LiveFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _LiveFinder())

VERSION = "7.9.0"
