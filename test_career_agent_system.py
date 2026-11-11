#!/usr/bin/env python3
"""Unified test runner for Career Agent System v6.5.0 (runs all 66 unit & integration tests in tests/)."""
import importlib.abc, importlib.util, pathlib, sys, unittest

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

class _DirectFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        rel = fullname.replace(".", "/")
        pkg = _HERE / rel / "__init__.py"
        if pkg.is_file():
            return importlib.util.spec_from_file_location(fullname, pkg, submodule_search_locations=[str(pkg.parent)])
        mod = _HERE / (rel + ".py")
        if mod.is_file():
            return importlib.util.spec_from_file_location(fullname, mod)
        tmod = _HERE / "tests" / (rel + ".py")
        if tmod.is_file():
            return importlib.util.spec_from_file_location(fullname, tmod)
        return None

if not any(isinstance(f, _DirectFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _DirectFinder())

TEST_MODULES = [
    "tests.test_agents",
    "tests.test_builder",
    "tests.test_certs_memory",
    "tests.test_cli",
    "tests.test_pipeline",
    "tests.test_resume_scrape",
    "tests.test_sources_mail",
    "tests.test_vault",
    "tests.test_user_backend",
    "tests.test_html_pages",
    "tests.test_signin_browser",
    "tests.test_e2e",
    "tests.test_youtube",
]

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for mod_name in TEST_MODULES:
        suite.addTests(loader.loadTestsFromName(mod_name))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
