import requests

try:
    r = requests.get('http://localhost:8000/health', timeout=3)
    print('Health:', r.status_code, r.json())
except Exception as e:
    print('Error:', e)
