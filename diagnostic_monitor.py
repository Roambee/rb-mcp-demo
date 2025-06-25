#!/usr/bin/env python3
"""
Diagnostic Monitor for Roambee MCP Demo
Monitors logs and provides real-time debugging information for multi-user issues
"""

import os
import time
import json
import requests
import threading
from datetime import datetime, timedelta
from collections import defaultdict, deque
import re

class DiagnosticMonitor:
    def __init__(self, server_url="http://localhost:4444", log_file="logs/app.log"):
        self.server_url = server_url
        self.log_file = log_file
        self.error_patterns = {
            'session_expired': r'❌ Invalid session for user',
            'rate_limit': r'⚠️.*Rate limit exceeded',
            'timeout': r'❌.*timeout',
            'connection_error': r'❌.*connection',
            'api_error': r'❌.*API.*error',
            'browser_fingerprint': r'⚠️.*Browser fingerprint',
            'mcp_connection': r'❌.*Failed to connect to Roambee MCP server',
            'unexpected_error': r'❌ Unexpected error'
        }
        
        self.error_counts = defaultdict(int)
        self.error_timeline = deque(maxlen=1000)  # Keep last 1000 errors
        self.user_errors = defaultdict(lambda: defaultdict(int))
        self.is_monitoring = False
        
    def start_monitoring(self):
        """Start monitoring logs and server health"""
        self.is_monitoring = True
        print(f"🔍 Starting diagnostic monitor for {self.server_url}")
        print(f"📊 Monitoring log file: {self.log_file}")
        
        # Start log monitoring thread
        log_thread = threading.Thread(target=self._monitor_logs, daemon=True)
        log_thread.start()
        
        # Start health check thread
        health_thread = threading.Thread(target=self._monitor_health, daemon=True)
        health_thread.start()
        
        # Main monitoring loop
        try:
            while self.is_monitoring:
                self._print_status()
                time.sleep(30)  # Print status every 30 seconds
        except KeyboardInterrupt:
            print("\n🛑 Stopping diagnostic monitor...")
            self.is_monitoring = False
    
    def _monitor_logs(self):
        """Monitor log file for errors"""
        if not os.path.exists(self.log_file):
            print(f"⚠️  Log file {self.log_file} not found")
            return
        
        # Start from end of file
        with open(self.log_file, 'r') as f:
            f.seek(0, 2)  # Go to end of file
            
            while self.is_monitoring:
                line = f.readline()
                if line:
                    self._analyze_log_line(line.strip())
                else:
                    time.sleep(0.1)  # Short sleep when no new lines
    
    def _analyze_log_line(self, line):
        """Analyze a log line for errors and patterns"""
        try:
            # Extract timestamp and user ID if present
            timestamp = datetime.now()
            user_id = "unknown"
            
            # Look for user ID in log line
            user_match = re.search(r'user (\w+)', line)
            if user_match:
                user_id = user_match.group(1)
            
            # Check against error patterns
            for error_type, pattern in self.error_patterns.items():
                if re.search(pattern, line):
                    self.error_counts[error_type] += 1
                    self.user_errors[user_id][error_type] += 1
                    self.error_timeline.append({
                        'timestamp': timestamp,
                        'error_type': error_type,
                        'user_id': user_id,
                        'line': line[:200]  # First 200 chars
                    })
                    
                    # Print critical errors immediately
                    if error_type in ['unexpected_error', 'mcp_connection', 'api_error']:
                        print(f"🚨 CRITICAL ERROR - {error_type} for user {user_id}")
                        print(f"   {line[:300]}")
                    
        except Exception as e:
            print(f"Error analyzing log line: {e}")
    
    def _monitor_health(self):
        """Monitor server health endpoint"""
        while self.is_monitoring:
            try:
                response = requests.get(f"{self.server_url}/health-check", timeout=5)
                if response.status_code == 200:
                    health_data = response.json()
                    if health_data.get('status') != 'healthy':
                        print(f"⚠️  Server health warning: {health_data}")
                else:
                    print(f"⚠️  Health check failed: HTTP {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Health check connection failed: {e}")
            
            time.sleep(60)  # Check every minute
    
    def _print_status(self):
        """Print current monitoring status"""
        print("\n" + "="*80)
        print(f"📊 DIAGNOSTIC STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)
        
        # Error summary
        if self.error_counts:
            print("\n🚨 ERROR SUMMARY (Total):")
            for error_type, count in sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   {error_type}: {count}")
        else:
            print("\n✅ No errors detected")
        
        # Recent errors (last 10 minutes)
        recent_cutoff = datetime.now() - timedelta(minutes=10)
        recent_errors = [e for e in self.error_timeline if e['timestamp'] > recent_cutoff]
        
        if recent_errors:
            print(f"\n⏰ RECENT ERRORS (Last 10 minutes): {len(recent_errors)}")
            error_types = defaultdict(int)
            for error in recent_errors:
                error_types[error['error_type']] += 1
            
            for error_type, count in error_types.items():
                print(f"   {error_type}: {count}")
        
        # Top problematic users
        if self.user_errors:
            print("\n👥 TOP USERS WITH ERRORS:")
            user_totals = {uid: sum(errors.values()) for uid, errors in self.user_errors.items()}
            top_users = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)[:5]
            
            for user_id, total_errors in top_users:
                if total_errors > 0:
                    print(f"   {user_id}: {total_errors} errors")
        
        # Server status
        try:
            response = requests.get(f"{self.server_url}/health-check", timeout=5)
            if response.status_code == 200:
                health = response.json()
                print(f"\n🏥 SERVER STATUS:")
                print(f"   Status: {health.get('status', 'unknown')}")
                print(f"   Uptime: {health.get('uptime_formatted', 'unknown')}")
                if 'session_stats' in health:
                    stats = health['session_stats']
                    print(f"   Active Sessions: {stats.get('active_sessions', 0)}/{stats.get('max_users', 0)}")
            else:
                print(f"\n❌ SERVER STATUS: HTTP {response.status_code}")
        except:
            print(f"\n❌ SERVER STATUS: Connection failed")
        
        print("\n" + "="*80)
    
    def generate_report(self):
        """Generate a detailed diagnostic report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_errors': sum(self.error_counts.values()),
                'error_types': dict(self.error_counts),
                'affected_users': len(self.user_errors),
                'monitoring_duration': 'unknown'
            },
            'user_breakdown': dict(self.user_errors),
            'recent_errors': [
                {
                    'timestamp': e['timestamp'].isoformat(),
                    'error_type': e['error_type'],
                    'user_id': e['user_id'],
                    'message': e['line']
                }
                for e in list(self.error_timeline)[-50:]  # Last 50 errors
            ]
        }
        
        report_file = f"diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 Diagnostic report saved to: {report_file}")
        return report_file

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Roambee MCP Demo Diagnostic Monitor')
    parser.add_argument('--server-url', default='http://localhost:4444', 
                       help='Server URL to monitor (default: http://localhost:4444)')
    parser.add_argument('--log-file', default='logs/app.log',
                       help='Log file to monitor (default: logs/app.log)')
    parser.add_argument('--report-only', action='store_true',
                       help='Generate report and exit (no continuous monitoring)')
    
    args = parser.parse_args()
    
    monitor = DiagnosticMonitor(args.server_url, args.log_file)
    
    if args.report_only:
        print("📊 Analyzing existing logs...")
        # Quick analysis of existing logs
        if os.path.exists(args.log_file):
            with open(args.log_file, 'r') as f:
                for line in f:
                    monitor._analyze_log_line(line.strip())
        
        report_file = monitor.generate_report()
        print(f"✅ Report generated: {report_file}")
    else:
        monitor.start_monitoring()

if __name__ == "__main__":
    main() 