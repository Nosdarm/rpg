import json
from sqlalchemy.types import TypeDecorator, TEXT, JSON
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB

# This will be our custom type for SQLite
class JsonBForSQLite(TypeDecorator):
    impl = TEXT
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value

# This will be our main JSONB type
# It will switch between the PostgreSQL JSONB type and our custom SQLite type
class JSONB(TypeDecorator):
    impl = JSON

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PGJSONB())
        else:
            return dialect.type_descriptor(JsonBForSQLite())
