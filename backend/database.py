#!/usr/bin/env python

#-----------------------------------------------------------------------
# database.py
# Picks the database backend. Wanted to figure out the database stuff cause my parts depend so much on in even without the postgre.
#
#   DATABASE_URL set in .env (or the environment)  -> databasepostgresql
#   DATABASE_URL not set                            -> databasesqlite
#
# So: on a laptop with no .env, the app runs against backend/roh.sqlite
# (build it from roh.sql). With a Neon connection string in .env, the
# same code runs against Neon (build it from roh_postgres.sql).
#
# Dondero ships database.py / databasesqlite.py / databasepostgresql.py
# side by side and copies one over database.py in his pennywise app; 
# doing same here
#-----------------------------------------------------------------------

import os
import dotenv

dotenv.load_dotenv()

if os.environ.get('DATABASE_URL'):
    from databasepostgresql import *
else:
    from databasesqlite import *
