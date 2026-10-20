"""Download the raw files if missing and verify them against the pinned sha256 in the config."""
import hashlib
import sys
import urllib.request
from pathlib import Path

import yaml


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(cfg_path="configs/default.yaml", strict=True):
    cfg = yaml.safe_load(open(cfg_path))
    raw = Path(cfg["raw_dir"]); raw.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, src in cfg["sources"].items():
        p = raw / name
        if not p.exists():
            print(f"downloading {name}"); urllib.request.urlretrieve(src["url"], p)
        got = sha256(p)
        match = got == src["sha256"]
        ok &= match
        print(f"{name}: {'OK' if match else 'CHECKSUM CHANGED ' + got}")
    if strict and not ok:
        sys.exit("Source data changed since the pinned download. Review, then update the sha256 in the config.")


if __name__ == "__main__":
    main(*sys.argv[1:2])
