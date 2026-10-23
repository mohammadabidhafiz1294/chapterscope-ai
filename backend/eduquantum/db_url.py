"""Pure helpers for parsing Django DATABASE_URL values.

Kept free of Django imports so it can be unit-tested without loading
settings. Supports SQLite, PostgreSQL and MySQL URL forms, including
percent-encoded credentials, IPv6 hosts, explicit ports and driver
option query parameters (e.g. ``?sslmode=require``).
"""

import os
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

SQLITE_SCHEMES = ("sqlite", "sqlite3")
POSTGRES_ENGINES = {
    "postgres": "django.db.backends.postgresql",
    "postgresql": "django.db.backends.postgresql",
    "postgresql+psycopg2": "django.db.backends.postgresql",
    "postgresql+psycopg": "django.db.backends.postgresql",
}
MYSQL_ENGINES = {
    "mysql": "django.db.backends.mysql",
    "mysqlclient": "django.db.backends.mysql",
}

# Query parameters consumed by Django's database engines rather than
# passed through verbatim as OPTIONS entries.
_QUERY_TO_ENGINE_OPTION = {"sslmode": "sslmode"}


def _sqlite_name(parsed) -> str:
    name = unquote(parsed.path or "")
    if name.startswith("//"):
        # sqlite:////absolute/path -> path is //absolute/path
        name = name[1:]
    elif name.startswith("/"):
        # sqlite:///relative/path -> path is /relative/path
        name = name[1:]
    return name


def _query_options(query: str) -> Dict[str, Any]:
    options: Dict[str, Any] = {}
    for raw_key, raw_value in parse_qsl(query, keep_blank_values=True):
        key = raw_key.strip()
        if not key:
            continue
        if key in _QUERY_TO_ENGINE_OPTION:
            options[_QUERY_TO_ENGINE_OPTION[key]] = raw_value
        else:
            options[key] = raw_value
    return options


def database_from_url(url: str, *, base_dir: Optional[str] = None) -> dict:
    """Build a Django ``DATABASES['default']`` entry from a DATABASE_URL.

    ``base_dir`` is only used to resolve relative SQLite paths.
    Raises ``ImproperlyConfigured`` for unsupported schemes.
    """
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        raise ImproperlyConfigured(
            "DATABASE_URL must include a scheme, e.g. "
            "sqlite:///db.sqlite3 or postgresql://user:pw@host/db"
        )

    if parsed.scheme in SQLITE_SCHEMES:
        name = _sqlite_name(parsed)
        if not name:
            name = "db.sqlite3"
        if base_dir is not None and not _is_absolute(name):
            name = f"{base_dir.rstrip('/')}/{name}"
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": name,
        }

    engine = POSTGRES_ENGINES.get(parsed.scheme) or MYSQL_ENGINES.get(
        parsed.scheme
    )
    if engine is None:
        raise ImproperlyConfigured(
            f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}"
        )

    config: dict = {
        "ENGINE": engine,
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }
    options = _query_options(parsed.query)
    if engine == "django.db.backends.mysql":
        options.setdefault("charset", "utf8mb4")
    if options:
        config["OPTIONS"] = options
    return config


def _is_absolute(path: str) -> bool:
    return os.path.isabs(path)
