"""Move Tab's stored secrets from one SECRET_KEY to another, so the key can be changed without re-entering anything.

Tab encrypts the credentials it stores (the Okta API token, every connector's credentials, workflow webhook URLs) with a key
derived from SECRET_KEY. Change SECRET_KEY and those can no longer be read. This tool re-encrypts them under the new key.

  Preview (changes nothing):   python -m app.scripts.rotate_secret_key
  Do it:                       python -m app.scripts.rotate_secret_key --apply

Run it inside the api container AFTER the new SECRET_KEY is set and deployed. The old key defaults to Tab's built-in
default; if you are rotating from some other key, pass it with --old-key.

Safe by design: the preview is the default; the whole change is one database transaction (all or nothing); every rewritten
value is read back and checked before it is committed; values already under the new key are left alone, so running it twice
is harmless; and a value that can't be read with either key is reported and never touched.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
from collections import Counter

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text

DEFAULT_OLD_KEY = "change-me-in-production"
INSECURE_KEYS = {"", DEFAULT_OLD_KEY}

DISCOVER = (
    "SELECT c.table_name, c.column_name FROM information_schema.columns c "
    "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE' "
    "WHERE c.table_schema = current_schema() AND c.column_name LIKE '%\\_encrypted' ESCAPE '\\' ORDER BY c.table_name, c.column_name"
)
PRIMARY_KEY = (
    "SELECT kcu.column_name FROM information_schema.table_constraints tc "
    "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name "
    "AND kcu.table_schema = tc.table_schema AND kcu.table_name = tc.table_name "
    "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = current_schema() AND tc.table_name = :t "
    "ORDER BY kcu.ordinal_position"
)


class RotationError(Exception):
    pass


def fernet_for(secret: str) -> Fernet:
    """The same derivation the app uses (app/core/encryption.py): SHA-256 of the key, url-safe base64."""
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def classify(token, old_f: Fernet, new_f: Fernet):
    """('rotate', new_token) | ('already', None) | ('unreadable', None) | ('empty', None)"""
    if token is None or str(token).strip() == "":
        return "empty", None
    raw = str(token).encode()
    try:
        plain = old_f.decrypt(raw)
    except InvalidToken:
        try:
            new_f.decrypt(raw)
            return "already", None
        except InvalidToken:
            return "unreadable", None
    return "rotate", new_f.encrypt(plain).decode()


def check_keys(old_key: str, new_key: str):
    """A reason this run must not go ahead, or None."""
    if new_key == old_key:
        return "SECRET_KEY in this container is still the old value. Set the new SECRET_KEY, redeploy, then run this again."
    if new_key in INSECURE_KEYS:
        return "The new SECRET_KEY is empty or the public default, which is not private. Set a long random value first."
    if len(new_key) < 16:
        return "The new SECRET_KEY is very short. Use a long random value (for example: openssl rand -hex 32)."
    return None


async def rotate(conn, old_key: str, new_key: str, apply: bool) -> dict:
    old_f, new_f = fernet_for(old_key), fernet_for(new_key)
    columns = (await conn.execute(text(DISCOVER))).all()
    report, todo = [], []
    for table, column in columns:
        pk_rows = (await conn.execute(text(PRIMARY_KEY), {"t": table})).all()
        if len(pk_rows) != 1:
            raise RotationError(f"{table} has no single-column primary key, so {column} can't be rotated safely. Nothing was changed.")
        pk = pk_rows[0][0]
        rows = (await conn.execute(text(f"SELECT {quote(pk)}, {quote(column)} FROM {quote(table)}"))).all()
        counts = Counter()
        for row_id, token in rows:
            action, new_token = classify(token, old_f, new_f)
            counts[action] += 1
            if action == "rotate":
                todo.append((table, column, pk, row_id, new_token))
        report.append({"table": table, "column": column, "rows": len(rows), "rotate": counts["rotate"], "already": counts["already"],
                       "unreadable": counts["unreadable"], "empty": counts["empty"]})
    if apply:
        for table, column, pk, row_id, new_token in todo:
            await conn.execute(text(f"UPDATE {quote(table)} SET {quote(column)} = :v WHERE {quote(pk)} = :id"), {"v": new_token, "id": row_id})
        for table, column, pk, row_id, new_token in todo:                      # read every rewritten value back before anything is committed
            back = (await conn.execute(text(f"SELECT {quote(column)} FROM {quote(table)} WHERE {quote(pk)} = :id"), {"id": row_id})).scalar_one_or_none()
            if back != new_token or classify(back, old_f, new_f)[0] != "already":
                raise RotationError(f"Could not confirm {table}.{column} was rewritten correctly. Nothing was changed.")
    return {"report": report, "would_rotate": len(todo), "rotated": len(todo) if apply else 0,
            "unreadable": sum(r["unreadable"] for r in report), "applied": apply}


def describe(result: dict) -> str:
    lines = []
    for r in result["report"]:
        lines.append(f"  {r['table']}.{r['column']}: {r['rotate']} to re-encrypt, {r['already']} already on the new key, "
                     f"{r['unreadable']} unreadable, {r['empty']} empty")
    if not result["report"]:
        lines.append("  (no encrypted columns found)")
    if result["applied"]:
        lines.append(f"\nDone: {result['rotated']} stored secret(s) are now encrypted with the new SECRET_KEY.")
    else:
        lines.append(f"\nPreview only: {result['would_rotate']} stored secret(s) would be re-encrypted. Nothing was changed. Run again with --apply to do it.")
    if result["unreadable"]:
        lines.append(f"Note: {result['unreadable']} value(s) can't be read with either key (they were already unreadable). They were left alone; re-enter those credentials in Tab.")
    return "\n".join(lines)


async def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Re-encrypt Tab's stored secrets under a new SECRET_KEY.")
    parser.add_argument("--old-key", default=DEFAULT_OLD_KEY, help="the SECRET_KEY the secrets are currently encrypted with (default: Tab's built-in default)")
    parser.add_argument("--apply", action="store_true", help="make the change (without this, only a preview is shown)")
    args = parser.parse_args(argv)

    from app.core.config import settings
    from app.db.session import engine

    problem = check_keys(args.old_key, settings.SECRET_KEY)
    if problem:
        print(problem)
        return 2
    try:
        async with engine.begin() as conn:                   # one transaction: any error undoes everything
            result = await rotate(conn, args.old_key, settings.SECRET_KEY, args.apply)
    except RotationError as e:
        print(f"Stopped: {e}")
        return 1
    finally:
        await engine.dispose()
    print(describe(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
