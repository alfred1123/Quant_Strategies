"""One-off login diagnostic — uses the same conninfo + AuthService as the API.

Usage:
    cd /home/alfcheun/workspace/Quant_Strategies
    source env/bin/activate && source .env
    python scripts/diag_login.py testuser '<the password you type in the form>'
"""


import logging
import os
import sys

from quant.api.auth.repo import AuthRepo
from quant.api.auth.service import AuthService
from quant.shared.config import _build_db_conninfo

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

if len(sys.argv) != 3:
    print("usage: python scripts/diag_login.py <username> <password>", file=sys.stderr)
    sys.exit(2)

username, password = sys.argv[1], sys.argv[2]

conninfo = _build_db_conninfo()
masked = conninfo.replace("password=" + (conninfo.split("password=")[1].split(" ")[0] if "password=" in conninfo else ""), "password=***")
print(f"[diag] conninfo: {masked}")

repo = AuthRepo(conninfo)
auth = AuthService()

# Step 1: raw lookup
row = repo.get_user_by_username(username.strip().casefold())
if row is None:
    print(f"[diag] DB lookup returned NO ROW for username={username!r}")
    sys.exit(1)
print(f"[diag] DB row: id={row['app_user_id']}  active={row['is_active_ind']!r}  hash_len={len(row['password_hash'])}  hash_prefix={row['password_hash'][:16]!r}  session_gen={row['session_gen']}")

# Step 2: verify
user = auth.verify_credentials(repo, username, password)
print(f"[diag] verify_credentials returned: {user}")
