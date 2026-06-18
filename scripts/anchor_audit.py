"""Create a local file TSA anchor for an audit JSONL file.

Optionally produce a full 国密证据链: SM3 hash chain anchor + SM2-signed TSA
timestamp token (GB/T 32918), satisfying the PRD §2.2/§4.5 'SM3 + SM2 + TSA'
audit evidence shape.

Usage:
    PYTHONPATH=src python scripts/anchor_audit.py --path logs/audit/audit.jsonl

    # Full 国密 chain: SM3 anchor + SM2 TSA token (generates a TSA keypair if needed)
    PYTHONPATH=src python scripts/anchor_audit.py --path logs/audit/audit.jsonl \\
        --algo sm3 --tsa-key logs/audit/anchors/tsa.key --gen-tsa-key \\
        --tsa-token-path logs/audit/anchors/tsa.token.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xa_guard.audit.tsa import create_file_anchor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="logs/audit/audit.jsonl")
    parser.add_argument("--anchor-path", help="where to write the anchor manifest")
    parser.add_argument("--index-path", help="where to append the anchor index JSONL")
    parser.add_argument("--no-index", action="store_true", help="write only the anchor manifest")
    parser.add_argument("--algo", choices=["sha256", "sm3"], default="sha256")
    parser.add_argument(
        "--tsa-key",
        help="SM2 keyfile for TSA timestamp token (private+public hex). Required for SM2 TSA token.",
    )
    parser.add_argument(
        "--gen-tsa-key",
        action="store_true",
        help="generate a new SM2 TSA keypair at --tsa-key if it does not exist",
    )
    parser.add_argument(
        "--tsa-token-path",
        help="where to write the SM2-signed TSA timestamp token JSON",
    )
    parser.add_argument(
        "--external-tsa-url",
        help="optional external RFC 3161 TSA URL to also query (best-effort, network)",
    )
    args = parser.parse_args()

    tsa_key = args.tsa_key
    if args.gen_tsa_key and tsa_key:
        kp = Path(tsa_key)
        if not kp.exists():
            try:
                from xa_guard.audit.sm_crypto import generate_sm2_keypair, write_sm2_keyfile

                priv, pub = generate_sm2_keypair()
                write_sm2_keyfile(kp, priv, pub)
                print(f"generated SM2 TSA keypair at {kp}", file=sys.stderr)
            except Exception as exc:
                print(f"failed to generate SM2 TSA keypair (gmssl unavailable?): {exc}", file=sys.stderr)
                tsa_key = None

    try:
        result = create_file_anchor(
            args.path,
            anchor_path=args.anchor_path,
            index_path=args.index_path,
            algo=args.algo,
            update_index=not args.no_index,
            tsa_key_path=tsa_key,
            tsa_token_path=args.tsa_token_path,
            external_tsa_url=args.external_tsa_url,
        )
    except Exception as exc:
        print(f"failed to create audit anchor: {exc}", file=sys.stderr)
        return 1

    out = {
        "audit_path": str(result.audit_path),
        "anchor_path": str(result.anchor_path),
        "record_count": result.manifest["record_count"],
        "anchored_record_hash": result.manifest["anchored_record_hash"],
        "anchor_sequence": result.manifest["anchor_sequence"],
        "previous_anchor_hash": result.manifest["previous_anchor_hash"],
        "anchor_index_path": result.manifest["anchor_index_path"],
        "tsa_token": result.manifest["tsa_token"],
    }
    if result.manifest.get("sm2_tsa_token_path"):
        out["sm2_tsa_token_path"] = result.manifest["sm2_tsa_token_path"]
        out["sm2_tsa_signature_algo"] = result.manifest.get("sm2_tsa_signature_algo", "")
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
