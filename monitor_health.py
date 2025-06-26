#!/usr/bin/env python3
import requests
import time
import json
from datetime import datetime

def monitor_health():
    """Monitor application health"""
    endpoints = [
        'http://localhost:8000/health-check',
        'http://localhost:8000/session-info'
    ]
    
    while True:
        print(f"\n[{datetime.now()}] Health Check:")
        
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, timeout=5)
                status = "✅ OK" if response.status_code == 200 else f"❌ {response.status_code}"
                print(f"  {endpoint}: {status}")
                
                if response.headers.get('content-type', '').startswith('application/json'):
                    data = response.json()
                    if 'active_sessions' in data:
                        print(f"    Active sessions: {data['active_sessions']}")
                        
            except Exception as e:
                print(f"  {endpoint}: ❌ ERROR - {str(e)}")
        
        time.sleep(30)

if __name__ == "__main__":
    monitor_health()
