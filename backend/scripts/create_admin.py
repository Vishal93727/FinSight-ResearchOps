"""Create a first platform administrator interactively; credentials are never written to disk."""

import argparse
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from finsight.core.security import ensure_role, hash_password
from finsight.infrastructure.database.session import SessionLocal
from finsight.identity.models import User


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.email.strip()):
        print("A valid email address is required", file=sys.stderr)
        return 2
    password = getpass.getpass("New administrator password (10+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        print("Passwords do not match", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        email = args.email.strip().lower()
        if db.scalar(select(User).where(User.email == email)):
            print("A user with that email already exists", file=sys.stderr)
            return 2
        admin = User(email=email, full_name=args.name.strip(), password_hash=hash_password(password))
        admin.roles.append(ensure_role(db, "ADMIN"))
        db.add(admin)
        db.commit()
        print(f"Administrator created: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
