"""Clear the Ops application's PostgreSQL data without rolling back its schema."""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine, inspect, text

from app.config import get_settings
from app.db.base import Base
import app.db.models  # noqa: F401 - register the application's tables


SCHEMA = "public"
MIGRATION_TABLE = "alembic_version"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="clear data; without this flag, only show row counts"
    )
    parser.add_argument(
        "--confirm-db", metavar="NAME", help="required with --execute; must match the connected database"
    )
    args = parser.parse_args()

    if args.execute and not args.confirm_db:
        parser.error("--execute requires --confirm-db NAME")

    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        if engine.dialect.name != "postgresql":
            parser.error("this rollback supports PostgreSQL only")

        with engine.begin() as conn:
            database_name = conn.scalar(text("SELECT current_database()"))
            if args.execute and args.confirm_db != database_name:
                parser.error(f"--confirm-db does not match the connected database ({database_name})")

            existing = set(inspect(conn).get_table_names(schema=SCHEMA))
            if MIGRATION_TABLE not in existing:
                parser.error(f"{MIGRATION_TABLE} is missing; database migrations have not been applied")
            expected = {table.name for table in Base.metadata.tables.values()}
            missing = expected - existing
            if missing:
                parser.error(f"application tables are missing: {', '.join(sorted(missing))}")

            tables = sorted(existing - {MIGRATION_TABLE})
            if not tables:
                parser.error("no data tables found")

            quote = conn.dialect.identifier_preparer.quote_identifier
            qualified = [f"{quote(SCHEMA)}.{quote(table)}" for table in tables]
            print(f"Database: {database_name}; schema: {SCHEMA}")
            for table, name in zip(tables, qualified):
                count = conn.exec_driver_sql(f"SELECT count(*) FROM {name}").scalar_one()
                print(f"  {table}: {count}")

            if args.execute:
                # One transaction: a failed TRUNCATE leaves all rows and sequences intact.
                # Omitting CASCADE makes unexpected cross-schema references fail safely.
                conn.exec_driver_sql(f"TRUNCATE TABLE {', '.join(qualified)} RESTART IDENTITY")
                print("Cleared all listed tables; kept schema and alembic_version.")
            else:
                print("Preview only. Add --execute --confirm-db NAME to clear these tables.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
