# Shared helpers for tools/evidence scripts. POSIX sh; source, do not execute.
# Works on Linux and Git Bash (Windows).

utc_stamp() { date -u +%Y%m%dT%H%M%SZ; }
utc_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*" >&2; }

# EVIDENCE-LAYOUT-SPEC.md §1: fixed roots per platform, XA_EVIDENCE_ROOT overrides.
evidence_root() {
    if [ -n "${XA_EVIDENCE_ROOT:-}" ]; then
        printf '%s\n' "$XA_EVIDENCE_ROOT"
        return
    fi
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*) printf 'D:/xa-evidence\n' ;;
        *) printf '%s/xa-evidence\n' "$HOME" ;;
    esac
}

# Prefer python3 but verify it actually runs: on Windows, python3 may be the
# Microsoft Store stub that exits non-zero without doing anything.
find_python() {
    for candidate in python3 python; do
        if "$candidate" -c pass >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    die "no working python3/python found (required for JSON handling)"
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        die "sha256sum/shasum not found"
    fi
}

short_host() {
    hostname 2>/dev/null | cut -d. -f1 | tr 'A-Z' 'a-z'
}

require_gnu_tar() {
    tar --version 2>/dev/null | head -n1 | grep -q 'GNU tar' \
        || die "GNU tar is required for deterministic sealing (spec §3)"
}
