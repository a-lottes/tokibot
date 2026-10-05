"""App updates without reflashing.

An update bundle is a .tar.gz with the claudegotchi/ package inside. It is unpacked
to /data/app, which the service runner (claudegotchi-run) puts in front of the
built-in copy. If the new version keeps crashing at start, the runner moves it
aside and falls back to the built-in one. Only the Python app is updated this way;
kernel and system changes still need a new image.
"""
import io
import os
import shutil
import subprocess
import sys
import tarfile

import claudegotchi

APP_DIR = "/data/app"
MAX_BUNDLE = 20 * 1024 * 1024


class UpdateError(Exception):
    pass


def running_from(app_dir=APP_DIR):
    here = os.path.dirname(os.path.abspath(claudegotchi.__file__))
    return "update" if here.startswith(os.path.abspath(app_dir) + os.sep) else "built-in"


def _extract(data, dest):
    try:
        tar = tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")
    except (tarfile.TarError, OSError) as e:
        raise UpdateError(f"not a .tar.gz bundle ({e})")
    with tar:
        for m in tar.getmembers():
            parts = m.name.replace("\\", "/").split("/")
            if (m.name.startswith("/") or ".." in parts or parts[0] != "claudegotchi"
                    or not (m.isfile() or m.isdir())):
                raise UpdateError(f"unexpected entry in bundle: {m.name}")
        for m in tar.getmembers():
            target = os.path.join(dest, *m.name.replace("\\", "/").split("/"))
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with tar.extractfile(m) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


def install(data, app_dir=APP_DIR):
    """Unpack, check that it imports, then swap it in. Returns the new version."""
    if len(data) > MAX_BUNDLE:
        raise UpdateError("bundle too large")
    new, old = app_dir + ".new", app_dir + ".old"
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    try:
        _extract(data, new)
        if not os.path.exists(os.path.join(new, "claudegotchi", "__init__.py")):
            raise UpdateError("bundle has no claudegotchi/__init__.py")
        check = subprocess.run(
            [sys.executable, "-c",
             "import claudegotchi, claudegotchi.server, claudegotchi.renderer;"
             "print(claudegotchi.__version__)"],
            env=dict(os.environ, PYTHONPATH=new), cwd=new, capture_output=True, text=True, timeout=60)
        if check.returncode != 0:
            raise UpdateError("the new version does not start: "
                              + (check.stderr.strip().splitlines() or ["?"])[-1])
        version = check.stdout.strip()
    except Exception:
        shutil.rmtree(new, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(app_dir):
        os.rename(app_dir, old)
    os.rename(new, app_dir)
    subprocess.run(["sync"])
    return version


def reset(app_dir=APP_DIR):
    """Go back to the version built into the image."""
    shutil.rmtree(app_dir, ignore_errors=True)
    subprocess.run(["sync"])


def bundle(src_dir, out):
    """Pack src_dir/claudegotchi into a bundle (used by `make bundle`)."""
    with tarfile.open(out, "w:gz") as tar:
        tar.add(os.path.join(src_dir, "claudegotchi"), arcname="claudegotchi",
                filter=lambda t: None if "__pycache__" in t.name or t.name.endswith(".pyc") else t)


if __name__ == "__main__":
    bundle(sys.argv[1], sys.argv[2])
    print(f"Bundle {claudegotchi.__version__} → {sys.argv[2]}")
