from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB_TYPE
from sqlalchemy import JSON as SA_JSON # Renamed to avoid conflict with JSON from typing

# In SQLAlchemy 2.0, JSONB might need to be imported from sqlalchemy.dialects.postgresql
# and JSON from sqlalchemy.sql.sqltypes or just sqlalchemy directly.

class JsonBForSQLite(TypeDecorator):
    """
    Custom type that uses JSONB for PostgreSQL and JSON (backed by TEXT) for SQLite.
    SQLAlchemy's JSON type handles serialization/deserialization for SQLite.
    """
    impl = TEXT # Default implementation if dialect-specific not found
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            # Ensure PGJSONB is instantiated if it's a type constructor
            return dialect.type_descriptor(PGJSONB_TYPE())
        else:
            # Ensure JSON is instantiated
            return dialect.type_descriptor(SA_JSON())

    @property
    def python_type(self):
        # This hints to SQLAlchemy about the Python type being handled.
        # For JSON/JSONB, it's typically dict or list.
        # Since our fields are Mapped[Dict[...]] or Mapped[Optional[Union[List, Dict]]],
        # dict is a reasonable general assumption, or we might need to be more specific
        # if SQLAlchemy has issues. For now, 'dict' should cover most cases.
        # For Mapped[Optional[Union[List[Dict[str, Any]], Dict[str, Any]]]],
        # a more generic type or no specific python_type might be better,
        # letting SQLAlchemy infer from the dialect's JSON/JSONB handling.
        # However, explicitly stating `dict` often works for JSON-like structures.
        return dict
