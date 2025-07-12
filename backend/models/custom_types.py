from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB_TYPE
from sqlalchemy import JSON as SA_JSON # Renamed to avoid conflict with JSON from typing

# In SQLAlchemy 2.0, JSONB might need to be imported from sqlalchemy.dialects.postgresql
# and JSON from sqlalchemy.sql.sqltypes or just sqlalchemy directly.
