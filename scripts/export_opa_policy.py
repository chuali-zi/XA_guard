"""Export the effective LayeredPolicySource view as OPA-ready artifacts.

Usage:
    PYTHONPATH=src python scripts/export_opa_policy.py --out-dir bench/.log/opa-bundle
"""
from __future__ import annotations

import argparse
import json
import sys

from xa_guard.policy.layered import LayeredPolicySource
from xa_guard.policy.opa_export import write_opa_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="policies/baseline/manifest.yaml")
    parser.add_argument("--overlay-root", default="policies/overlay")
    parser.add_argument("--out-dir", default="bench/.log/opa-bundle")
    parser.add_argument("--package", default="xa_guard.gate3")
    args = parser.parse_args()

    source = LayeredPolicySource(manifest_path=args.manifest, overlay_root=args.overlay_root)
    manifest = write_opa_bundle(source, args.out_dir, package=args.package)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
