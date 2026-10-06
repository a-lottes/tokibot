#!/usr/bin/env python3
"""Packs the Claude Code plugin for the website.

Writes <out>/plugin/tokibot.zip and <out>/marketplace.json, so that
  /plugin marketplace add https://tokibot.lottes.dev/marketplace.json
works without access to the repository. The zip is deterministic: same
sources, same bytes, same sha256.

  python3 plugin/build.py docs [https://tokibot.lottes.dev]
"""
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(HERE, "tokibot")


def build(out, site):
    os.makedirs(os.path.join(out, "plugin"), exist_ok=True)
    zip_path = os.path.join(out, "plugin", "tokibot.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirnames, filenames in os.walk(PLUGIN, followlinks=True):
            dirnames.sort()
            for name in sorted(filenames):
                src = os.path.join(dirpath, name)
                rel = os.path.relpath(src, PLUGIN)
                info = zipfile.ZipInfo(rel.replace(os.sep, "/"), (2020, 1, 1, 0, 0, 0))
                info.external_attr = (0o755 if name.endswith((".py", ".sh")) else 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(src, "rb") as f:  # follows the symlink to client/
                    z.writestr(info, f.read())
    with open(zip_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as f:
        market = json.load(f)
    for entry in market["plugins"]:
        if entry["name"] == "tokibot":
            entry["source"] = {"source": "archive",
                               "url": site.rstrip("/") + "/plugin/tokibot.zip",
                               "sha256": sha}
    with open(os.path.join(out, "marketplace.json"), "w") as f:
        json.dump(market, f, indent=2)
        f.write("\n")
    print(f"plugin/tokibot.zip  sha256 {sha}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "docs",
          sys.argv[2] if len(sys.argv) > 2 else "https://tokibot.lottes.dev")
