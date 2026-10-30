#!/usr/bin/env python3
"""Stage or install only UREVO Local, without reloading or restarting HA."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path


def files_at(source):
    files = {
        p.name: p.read_bytes() for p in source.iterdir() if p.suffix in (".py", ".json")
    }
    icon = source / "brand/icon.png"
    if icon.is_file():
        files["brand/icon.png"] = icon.read_bytes()
    return files


def installed_files(target):
    """Include generated translations and reject hidden changes before replacement."""
    if target.is_symlink() or any(p.is_symlink() for p in target.rglob("*")):
        raise ValueError("Refusing a component containing symlinks")
    return {
        str(p.relative_to(target)): p.read_bytes()
        for p in target.rglob("*")
        if p.is_file() and "__pycache__" not in p.relative_to(target).parts
    }


def install(files, config_root, apply=False, upgrade=False):
    required = {
        "manifest.json",
        "strings.json",
        "__init__.py",
        "protocol.py",
        "steps.py",
        "coordinator.py",
        "config_flow.py",
        "entity.py",
        "sensor.py",
        "number.py",
        "button.py",
        "switch.py",
        "brand/icon.png",
    }
    if set(files) != required:
        raise ValueError("Unexpected integration file inventory")
    if json.loads(files["manifest.json"])["domain"] != "urevo_local":
        raise ValueError("Wrong domain")
    for name, content in files.items():
        if name.endswith(".py"):
            compile(content, name, "exec")
        elif name.endswith(".json"):
            json.loads(content)
    hashes = {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }
    expected_files = {**files, "translations/en.json": files["strings.json"]}
    target = config_root / "custom_components" / "urevo_local"
    receipt_path = config_root / ".urevo-local-install-receipt.json"
    if not (config_root / "configuration.yaml").is_file():
        raise ValueError("Not a Home Assistant config directory")
    installed = None
    backup = None
    if target.exists() or target.is_symlink():
        installed = installed_files(target)
        if installed == expected_files:
            print(
                json.dumps(
                    {
                        "status": "already_installed",
                        "target": str(target),
                        "hashes": hashes,
                    }
                )
            )
            return
        if not upgrade:
            raise ValueError(
                "Existing UREVO integration differs; refusing to overwrite it"
            )
        receipt = json.loads(receipt_path.read_text())
        expected_hashes = dict(receipt["hashes"])
        expected_hashes["translations/en.json"] = expected_hashes["strings.json"]
        actual_hashes = {
            name: hashlib.sha256(content).hexdigest()
            for name, content in installed.items()
        }
        if receipt["target"] != str(target) or actual_hashes != expected_hashes:
            raise ValueError(
                "Installed component differs from its receipt; preserving user changes"
            )
    if not apply:
        print(json.dumps({"status": "ready", "target": str(target), "hashes": hashes}))
        return
    target.parent.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".urevo-stage-", dir=config_root))
    for name, content in files.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (stage / "translations").mkdir()
    (stage / "translations" / "en.json").write_bytes(files["strings.json"])
    receipt = {
        "target": str(target),
        "previously_present": installed is not None,
        "hashes": hashes,
        "runtime_activated": False,
    }
    if installed is not None:
        if installed_files(target) != installed:
            raise ValueError("Component changed while preparing upgrade")
        backup = Path(tempfile.mkdtemp(prefix=".urevo-backup-", dir=config_root))
        (backup / "install-receipt.json").write_bytes(receipt_path.read_bytes())
        target.rename(backup / "urevo_local")
        receipt["backup"] = str(backup)
    elif target.exists():
        raise ValueError(
            "Destination appeared during installation; leaving stage untouched"
        )
    try:
        stage.rename(target)
    except OSError:
        if backup is not None and not target.exists():
            (backup / "urevo_local").rename(target)
        raise
    for name, digest in hashes.items():
        if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Installed file verification failed")
    if installed_files(target) != expected_files:
        raise ValueError("Installed content verification failed")
    with tempfile.NamedTemporaryFile(
        mode="w", dir=config_root, prefix=".urevo-receipt-", delete=False
    ) as handle:
        handle.write(json.dumps(receipt, indent=2) + "\n")
    Path(handle.name).replace(receipt_path)
    print(json.dumps({"status": "installed_pending_activation", **receipt}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "custom_components"
        / "urevo_local",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Back up and replace only a receipt-matching installation",
    )
    args = parser.parse_args()
    install(files_at(args.source), args.config_root, args.apply, args.upgrade)
