import os

# Ensure pure Python mode for SQLAlchemy if binary extensions are restricted
os.environ.setdefault("DISABLE_SQLALCHEMY_CEXT", "1")

__version__ = "0.1.0"
