"""
Database Schema Upgrade Script

This module handles automatic database schema updates when new columns or tables
are added to the models. It runs on application startup.

Uses SQLAlchemy introspection to detect missing columns and adds them automatically.
"""

import logging
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError

logger = logging.getLogger(__name__)


def get_existing_columns(inspector, table_name):
    """Get list of existing column names for a table."""
    try:
        columns = inspector.get_columns(table_name)
        return {col['name'] for col in columns}
    except Exception:
        return set()


def get_existing_tables(inspector):
    """Get list of existing table names."""
    return set(inspector.get_table_names())


def upgrade_database(db, app):
    """
    Automatically upgrade database schema to match current models.

    This function:
    1. Creates any missing tables
    2. Adds any missing columns to existing tables
    3. Handles the migration gracefully without data loss
    """
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = get_existing_tables(inspector)

        # Get all model tables
        model_tables = db.metadata.tables

        app.logger.info("Checking database schema for upgrades...")

        # First, create any completely missing tables
        for table_name, table in model_tables.items():
            if table_name not in existing_tables:
                app.logger.info(f"Creating new table: {table_name}")
                table.create(db.engine)

        # Refresh inspector after creating tables
        inspector = inspect(db.engine)

        # Now check for missing columns in existing tables
        for table_name, table in model_tables.items():
            existing_columns = get_existing_columns(inspector, table_name)

            for column in table.columns:
                if column.name not in existing_columns:
                    add_column(db, app, table_name, column)


def add_column(db, app, table_name, column):
    """Add a missing column to a table."""
    column_name = column.name
    column_type = column.type.compile(db.engine.dialect)

    # Build the ALTER TABLE statement
    nullable = "NULL" if column.nullable else "NOT NULL"

    # Handle default values
    default = ""
    if column.default is not None:
        if hasattr(column.default, 'arg'):
            default_val = column.default.arg
            if callable(default_val):
                # Skip callable defaults, they'll be handled by the app
                default = ""
            elif isinstance(default_val, str):
                default = f"DEFAULT '{default_val}'"
            elif isinstance(default_val, bool):
                default = f"DEFAULT {1 if default_val else 0}"
            else:
                default = f"DEFAULT {default_val}"

    # For NOT NULL columns without defaults, we need to provide a default
    if nullable == "NOT NULL" and not default:
        # Provide sensible defaults based on type
        type_str = str(column_type).upper()
        if 'INT' in type_str:
            default = "DEFAULT 0"
        elif 'VARCHAR' in type_str or 'TEXT' in type_str or 'STRING' in type_str:
            default = "DEFAULT ''"
        elif 'NUMERIC' in type_str or 'DECIMAL' in type_str or 'FLOAT' in type_str:
            default = "DEFAULT 0"
        elif 'BOOL' in type_str:
            default = "DEFAULT 0"
        else:
            # Make it nullable if we can't determine a default
            nullable = "NULL"

    # SQLite doesn't support adding NOT NULL columns without defaults well
    # So we'll make new columns nullable initially
    if db.engine.dialect.name == 'sqlite':
        nullable = "NULL"
        default = ""

    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} {nullable} {default}"

    try:
        app.logger.info(f"Adding column {table_name}.{column_name} ({column_type})")
        db.session.execute(text(sql.strip()))
        db.session.commit()
        app.logger.info(f"Successfully added column {table_name}.{column_name}")
    except (OperationalError, ProgrammingError) as e:
        db.session.rollback()
        # Column might already exist or other issue
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            app.logger.debug(f"Column {table_name}.{column_name} already exists")
        else:
            app.logger.warning(f"Could not add column {table_name}.{column_name}: {e}")


def ensure_platform_settings(db, app):
    """Ensure default platform settings exist."""
    from shkeeper.models import PlatformSettings

    with app.app_context():
        try:
            settings = PlatformSettings.query.first()
            if not settings:
                app.logger.info("Creating default platform settings...")
                settings = PlatformSettings(
                    id=1,
                    default_commission_percent=2.0,
                    default_commission_fixed=0,
                    min_payout_amount=50,
                    auto_approve_merchants=True
                )
                db.session.add(settings)
                db.session.commit()
                app.logger.info("Default platform settings created.")
        except Exception as e:
            db.session.rollback()
            app.logger.warning(f"Could not create platform settings: {e}")


def run_migrations(db, app):
    """
    Run all database migrations/upgrades.

    This is the main entry point called from create_app().
    """
    try:
        upgrade_database(db, app)
        ensure_platform_settings(db, app)
        app.logger.info("Database schema check complete.")
    except Exception as e:
        app.logger.error(f"Database migration error: {e}")
        # Don't raise - allow app to start even if migration fails
        # The specific features might not work but core functionality should
