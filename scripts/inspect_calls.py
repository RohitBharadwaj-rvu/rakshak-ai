import os
import json
import urllib.request
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

BOLNA_API_KEY = os.getenv('BOLNA_API_KEY')
agent_id = 'a6998177-c352-47b5-8867-4757b29416a9'

req = urllib.request.Request(
    f'https://api.bolna.ai/agent/{agent_id}/executions',
    headers={'Authorization': f'Bearer {BOLNA_API_KEY}'}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))

print(f'Total executions: {len(data)}')
for i, ex in enumerate(data[:5]):
    eid = ex.get('id')
    cat = ex.get('created_at')
    dur = ex.get('conversation_duration')
    stat = ex.get('status')
    hangup = ex.get('telephony_data', {}).get('hangup_by')
    print(f'[{i}] ID: {eid} | Time: {cat} | Dur: {dur}s | Status: {stat} | HangupBy: {hangup}')

print('\n' + '='*50 + '\n')
latest = data[0]
print(f'LATEST CALL: {latest.get("id")}')
print('TRANSCRIPT:')
print(latest.get('transcript'))
print('\nTELEPHONY DATA:')
print(json.dumps(latest.get('telephony_data', {}), indent=2))
print('\nLATENCY DATA:')
print(json.dumps(latest.get('latency_data', {}), indent=2))
