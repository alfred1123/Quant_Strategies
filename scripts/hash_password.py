"""Generate an Argon2id PHC-encoded password hash for CORE_ADMIN.APP_USER seeding.

Usage:
    python scripts/hash_password.py

Prompts twice (no echo), prints the PHC hash to stdout. All other output goes to
stderr so the hash is cleanly pipeable:

    HASH=$(python scripts/hash_password.py)
    psql ... -c "CALL CORE_ADMIN.SP_INS_APP_USER('alice', '$HASH', 'admin');"

Exit codes:
    0  success (hash printed)
    1  password mismatch
    2  password too short
    3  cancelled (Ctrl-C / EOF)
"""
from __future__ import annotations

import getpass
import sys

from argon2 import PasswordHasher

MIN_LENGTH = 12

# OWASP-recommended Argon2id parameters (~100 ms on a laptop CPU).
HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=4,
)


def main() -> int:
    try:
        pw1 = getpass.getpass("Password: ", stream=sys.stderr)
        pw2 = getpass.getpass("Confirm:  ", stream=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 3

    if pw1 != pw2:
        print("Error: passwords do not match.", file=sys.stderr)
        return 1

    if len(pw1) < MIN_LENGTH:
        print(f"Error: password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 2

    print(HASHER.hash(pw1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
