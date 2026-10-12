"""Build the Raspberry Pi Imager repository for the website's download page.

  python3 tools/imager_list.py <downloads dir> <tag> <release date> [site URL]

Writes imager.json and tokibot.rpi-imager-manifest (the same list) into the
downloads directory, next to the images of the latest release. Imager opens the
.rpi-imager-manifest file on a double click, or takes the URL of imager.json under
App Options → Content Repository. Unlike "Use custom", an image from this list
offers Imager's OS customisation: "init_format": "cloudinit" makes Imager write
the Wi-Fi and time zone onto the boot partition, where the gotchi's S04imager takes
them over on first boot (app/tokibot/imager.py). Releases from before that still
get listed, just without the customisation.
"""
import hashlib
import json
import lzma
import os
import sys

SITE = "https://tokibot.lottes.dev"
CUSTOMISATION_SINCE = (0, 5, 1)          # first release with S04imager

# (image, name, Imager's device tags) Tags as in Imager's own device list: the
# Zero 2 W counts as a Pi 3, the Zero W as a Pi 1.
IMAGES = [
    ("tokibot-zero2w.img.xz", "Tokibot for Raspberry Pi Zero 2 W", ["pi3-64bit"]),
    ("tokibot-zerow.img.xz", "Tokibot for Raspberry Pi Zero W", ["pi1-32bit"]),
]

DEVICES = [
    {"name": "Raspberry Pi Zero 2 W", "tags": ["pi3-64bit", "pi3-32bit"], "icon": "",
     "description": "Raspberry Pi Zero 2 W", "matching_type": "inclusive", "default": True},
    {"name": "Raspberry Pi Zero", "tags": ["pi1-32bit"], "icon": "",
     "description": "Raspberry Pi Zero W and Zero WH", "matching_type": "inclusive"},
]

DESCRIPTION = ("E-ink companion that shows how your Claude Code sessions are doing. "
               "Customisation: only Wi-Fi and time zone are used.")


def version(tag):
    try:
        return tuple(int(p) for p in tag.lstrip("v").split("-")[0].split("."))
    except ValueError:
        return ()


def sha256_and_size(path, unpack=False):
    h, size = hashlib.sha256(), 0
    with (lzma.open(path, "rb") if unpack else open(path, "rb")) as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def build(downloads, tag, released, site=SITE):
    """The repository as a dict, for the images present in downloads."""
    entries = []
    for name, title, tags in IMAGES:
        path = os.path.join(downloads, name)
        if not os.path.exists(path):
            continue
        download_sha, download_size = sha256_and_size(path)
        extract_sha, extract_size = sha256_and_size(path, unpack=True)
        entry = {
            "name": title,
            "description": DESCRIPTION,
            "icon": f"{site}/favicon.svg",
            "website": site,
            "url": f"{site}/downloads/{name}",
            "release_date": released[:10],
            "extract_size": extract_size,
            "extract_sha256": extract_sha,
            "image_download_size": download_size,
            "image_download_sha256": download_sha,
            "devices": tags,
        }
        if version(tag) >= CUSTOMISATION_SINCE:
            entry["init_format"] = "cloudinit"
        entries.append(entry)
    return {"imager": {"devices": DEVICES}, "os_list": entries}


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 2
    downloads, tag, released = argv[1:4]
    site = (argv[4] if len(argv) > 4 else SITE).rstrip("/")
    repo = build(downloads, tag, released, site)
    if not repo["os_list"]:
        print("No images, no Imager repository.")
        return 0
    text = json.dumps(repo, indent=2) + "\n"
    for name in ("imager.json", "tokibot.rpi-imager-manifest"):
        with open(os.path.join(downloads, name), "w") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
