"""Select the existing SQL adapter from the shared Flask configuration."""
import atexit
from flask import current_app


def init_app(app):
    if app.config['DATABASE_URL']:
        from psycopg_pool import ConnectionPool
        pool = ConnectionPool(app.config['DATABASE_URL'], open=False)
        app.extensions['database_pool'] = pool
        atexit.register(pool.close)


def __getattr__(name):
    if name.startswith('_'):
        raise AttributeError(name)
    if current_app.config['DATABASE_URL']:
        import databasepostgresql as adapter
    else:
        import databasesqlite as adapter
    return getattr(adapter, name)
