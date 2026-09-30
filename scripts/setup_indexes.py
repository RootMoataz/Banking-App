"""Create the MongoDB indexes the app relies on (the brief's "SQL script")."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.db import ensure_indexes, get_database  # noqa: E402


def main() -> None:
    db = get_database(load_settings())
    ensure_indexes(db)
    for name in ("customers", "accounts", "transactions", "alerts"):
        print(name, sorted(i["name"] for i in db[name].list_indexes()))


if __name__ == "__main__":
    main()
