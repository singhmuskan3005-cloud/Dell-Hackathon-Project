import asyncio
from app.database import fetch_all
try:
    res = fetch_all("SELECT id, user_id, name FROM participants WHERE id = '56b083e8-a12c-4a1b-945f-ebe41276f660' OR user_id = '56b083e8-a12c-4a1b-945f-ebe41276f660'")
    print("Participant exists:", len(res) > 0, res)
except Exception as e:
    print("Error:", e)
