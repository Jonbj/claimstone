"""Build a wheel offline in a temporary copy; check the actual distributed backend modules.

Run with a Python that already has setuptools (on the reviewed host: python3).
No dependencies are downloaded or installed. The source tree is never built in place.
"""

import contextlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

from setuptools import build_meta


def main():
    repo = pathlib.Path(__file__).resolve().parents[2]
    original = pathlib.Path.cwd()
    try:
        with tempfile.TemporaryDirectory(prefix="claimstone-wheel-review-") as temp:
            root = pathlib.Path(temp)
            for name in ("pyproject.toml", "README.md"):
                shutil.copy2(repo / name, root / name)
            shutil.copytree(repo / "claimstone", root / "claimstone",
                            ignore=shutil.ignore_patterns("__pycache__"))
            os.chdir(root)
            with contextlib.redirect_stdout(io.StringIO()):
                filename = build_meta.build_wheel(str(root / "dist"))
            wheel = root / "dist" / filename
            with zipfile.ZipFile(wheel) as archive:
                runners = [name for name in archive.namelist() if "/runners/" in name]
                assert not any(name.startswith(('projects/', 'store/')) for name in archive.namelist())
            print("wheel:", filename, "backend files:", len(runners))
            # -I -S excludes cwd, PYTHONPATH, site-packages and editable-install import hooks.
            # Importing claimstone.runners first requires no third-party dependency.
            dependencies = list(dict.fromkeys([str(p) for p in (repo / '.venv' / 'lib').glob('python*/site-packages')]
                                               + [sysconfig.get_path('purelib'), sysconfig.get_path('platlib')]))
            # Explicit dependency paths do not execute .pth editable hooks under -I -S.
            code = (f"import sys; sys.path[:0] = {[str(wheel), *dependencies]!r}; "
                    "import claimstone.cli, claimstone.runners; "
                    "assert set(claimstone.cli.BACKENDS) == set(claimstone.runners.available()); "
                    "assert 'claimstone.runners' in sys.modules; "
                    "print('installed CLI discovers all backends')")
            result = subprocess.run([sys.executable, "-I", "-S", "-c", code],
                                    cwd=root, capture_output=True, text=True, timeout=30)
            print(result.stderr.strip() or result.stdout.strip())
            return result.returncode
    finally:
        os.chdir(original)


if __name__ == "__main__":
    raise SystemExit(main())
