#!/usr/bin/env python

#-----------------------------------------------------------------------
# database.py
# Picks the database backend:
#   DATABASE_URL set (in .env)  -> databasepostgresql (Neon)
#   DATABASE_URL not set        -> databasesqlite (local roh.sqlite)
# Routes just do "import database".
#-----------------------------------------------------------------------

import os
import dotenv

dotenv.load_dotenv()

if os.environ.get('DATABASE_URL'):
    from databasepostgresql import *
else:
    from databasesqlite import *
