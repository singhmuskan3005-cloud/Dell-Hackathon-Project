import sys
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv(".env")
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
with conn.cursor() as cur:
    cur.execute("SELECT id, user_id, name FROM participants WHERE id = '56b083e8-a12c-4a1b-945f-ebe41276f660' OR user_id = '56b083e8-a12c-4a1b-945f-ebe41276f660'")
    print("Participant query result:", cur.fetchall())
