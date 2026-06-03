"""Generate all PDF fixtures and keep manifest.json up to date.

Usage as CLI:
    python -m tests.fixtures.generators.generate_all          # regenerate all
    python -m tests.fixtures.generators.generate_all grp_c   # regenerate one group

Usage as library (called from tests/integration/conftest.py):
    from tests.fixtures.generators.generate_all import hash_check_all
    hash_check_all()
"""

import hashlib
import importlib
import json
import sys
from pathlib import Path

_GENERATORS_DIR = Path(__file__).parent
_FIXTURES_DIR = _GENERATORS_DIR.parent
_PDFS_DIR = _FIXTURES_DIR / "pdfs"
_MANIFEST_PATH = _FIXTURES_DIR / "manifest.json"

# Map from manifest key to generator module name (grp_f excluded — no PDF output)
_GENERATOR_MAP: dict[str, str] = {
    "grp_a": "grp_a_native",
    "grp_b": "grp_b_classifier",
    "grp_c": "grp_c_blocktypes",
    "grp_d": "grp_d_metadata",
    "grp_e": "grp_e_multipage",
    "grp_g": "grp_g_layout",
    "grp_h": "grp_h_edge",
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest() -> dict:
    try:
        return json.loads(_MANIFEST_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_manifest(manifest: dict) -> None:
    _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")


def _run_generator(key: str, module_name: str, manifest: dict) -> bool:
    """Run one generator if its hash has changed or any output PDF is missing.
    Returns True if regeneration happened."""
    generator_path = _GENERATORS_DIR / f"{module_name}.py"
    current_hash = _file_hash(generator_path)

    entry = manifest.get(key, {})
    stored_hash = entry.get("hash", "")
    fixtures = entry.get("fixtures", [])

    needs_regen = current_hash != stored_hash or any(not (_PDFS_DIR / f).exists() for f in fixtures)
    if not needs_regen:
        return False

    module = importlib.import_module(f"tests.fixtures.generators.{module_name}")
    generated = module.generate(_PDFS_DIR)
    manifest[key] = {
        "hash": current_hash,
        "fixtures": [p.name for p in generated],
    }
    print(f"[generate_all] regenerated {key}: {[p.name for p in generated]}")
    return True


def hash_check_all(group: str | None = None) -> None:
    """Check all generators (or one group) and regenerate stale PDFs."""
    _PDFS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    updated = False

    generators = (
        {group: _GENERATOR_MAP[group]} if group and group in _GENERATOR_MAP else _GENERATOR_MAP
    )

    for key, module_name in generators.items():
        if _run_generator(key, module_name, manifest):
            updated = True

    if updated:
        _save_manifest(manifest)


if __name__ == "__main__":
    grp_arg = sys.argv[1].lower() if len(sys.argv) > 1 else None
    if grp_arg and grp_arg not in _GENERATOR_MAP:
        print(f"Unknown group '{grp_arg}'. Valid groups: {sorted(_GENERATOR_MAP)}", file=sys.stderr)
        sys.exit(1)
    hash_check_all(grp_arg)
