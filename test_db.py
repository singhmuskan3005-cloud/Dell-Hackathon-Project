import sys
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv(".env")
engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    res = conn.execute(text("SELECT id, user_id, name FROM participants WHERE id = '56b083e8-a12c-4a1b-945f-ebe41276f660' OR user_id = '56b083e8-a12c-4a1b-945f-ebe41276f660'"))
    print("Participant query result:", res.fetchall())
