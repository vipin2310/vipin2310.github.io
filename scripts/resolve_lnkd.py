"""Replace LinkedIn short links (https://lnkd.in/...) in content.yaml with the URLs they point to.

    uv run scripts/resolve_lnkd.py

LinkedIn's short links open an interstitial page that names the real target; this script reads that
target and rewrites content.yaml in place. Links that cannot be resolved are left unchanged.
"""
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = re.compile(r'data-tracking-control-name="external_url_click"[^>]*href="([^"]+)"')


def resolve(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        m = TARGET.search(r.read().decode("utf-8", "replace"))
    return m[1].replace("&amp;", "&") if m else None


def main():
    path = ROOT / "content.yaml"
    text = path.read_text(encoding="utf-8")
    for short in sorted(set(re.findall(r"https://lnkd\.in/[A-Za-z0-9_-]+", text))):
        target = resolve(short)
        print(f"{short} -> {target or 'NOT RESOLVED, kept'}")
        if target:
            text = text.replace(short, target)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
