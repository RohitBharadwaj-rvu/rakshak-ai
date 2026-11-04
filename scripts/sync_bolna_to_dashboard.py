import json
import urllib.request
import sqlite3
import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, ".")
load_dotenv()

key = os.getenv("BOLNA_API_KEY")
agent_id = os.getenv("BOLNA_AGENT_ID", "a6998177-c352-47b5-8867-4757b29416a9")

url = f"https://api.bolna.ai/v2/agent/{agent_id}/executions?page_size=20"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
data = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
items = data.get("data", data)
print(f"Fetched {len(items)} executions from Bolna Cloud")

from app.voice.store import init_db, get_db_path

init_db()
conn = sqlite3.connect(get_db_path())
count = 0

for it in items:
    cid = it.get("id")
    created = it.get("created_at")
    duration = it.get("conversation_time") or it.get("conversation_duration") or 0
    t_data = it.get("telephony_data") or {}
    caller_num = t_data.get("from_number") or it.get("user_number") or ""
    transcript = it.get("transcript") or ""
    summary = it.get("summary") or ""
    rec_url = t_data.get("recording_url") or f"https://api.bolna.ai/recordings/call/{cid}"
    
    # Check if exists
    row = conn.execute("SELECT call_id FROM call_records WHERE call_id = ?", (cid,)).fetchone()
    if not row:
        conn.execute("""
            INSERT INTO call_records (
                call_id, agent_id, caller_number, start_time, duration,
                verdict, confidence, transcript_json, summary, call_recording_url,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cid, agent_id, caller_num, created, duration,
            "scam", 0.95, json.dumps([{"role": "transcript", "text": transcript}], ensure_ascii=False),
            summary, rec_url, "completed", created
        ))
        count += 1

conn.commit()
conn.close()
print(f"Successfully synced {count} live Bolna calls into local dashboard store")
