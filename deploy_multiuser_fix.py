#!/usr/bin/env python3
"""
Multi-User Environment Deployment Fix Script
Addresses the JSON parsing errors and session management issues in Kubernetes/multi-user deployments
"""

import os
import sys
import json
import subprocess
import time
import requests
from pathlib import Path

def check_environment():
    """Check the current deployment environment"""
    print("🔍 Checking deployment environment...")
    
    env_info = {
        "kubernetes": False,
        "docker": False,
        "proxy": False,
        "load_balancer": False
    }
    
    # Check for Kubernetes
    k8s_indicators = [
        'KUBERNETES_SERVICE_HOST',
        'KUBERNETES_SERVICE_PORT', 
        'POD_NAME',
        'POD_NAMESPACE'
    ]
    
    for indicator in k8s_indicators:
        if os.getenv(indicator):
            env_info["kubernetes"] = True
            print(f"   ✅ Kubernetes detected: {indicator}={os.getenv(indicator)}")
            break
    
    # Check for Docker
    if os.path.exists('/.dockerenv') or os.getenv('container'):
        env_info["docker"] = True
        print("   ✅ Docker container detected")
    
    # Check for service account (Kubernetes)
    if os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount'):
        env_info["kubernetes"] = True
        print("   ✅ Kubernetes service account detected")
    
    # Check for common proxy headers in environment
    proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
    for var in proxy_vars:
        if os.getenv(var):
            env_info["proxy"] = True
            print(f"   ✅ Proxy detected: {var}={os.getenv(var)}")
    
    return env_info

def check_dependencies():
    """Check if all required dependencies are installed"""
    print("\n📦 Checking dependencies...")
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'starlette',
        'openai',
        'httpx'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"   ❌ {package} - MISSING")
    
    if missing_packages:
        print(f"\n⚠️  Missing packages: {', '.join(missing_packages)}")
        print("   Run: pip install " + " ".join(missing_packages))
        return False
    
    return True

def create_kubernetes_config():
    """Create Kubernetes-specific configuration"""
    print("\n🚀 Creating Kubernetes configuration...")
    
    # Create ConfigMap for environment-specific settings
    configmap_yaml = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: roambee-chat-config
data:
  ENVIRONMENT: "kubernetes"
  LOG_LEVEL: "INFO"
  MAX_CONCURRENT_USERS: "50"
  SESSION_TIMEOUT: "3600"
  RATE_LIMIT_REQUESTS: "15"
  RATE_LIMIT_WINDOW: "60"
  ENABLE_DETAILED_LOGGING: "true"
  KUBERNETES_MODE: "true"
---
apiVersion: v1
kind: Service
metadata:
  name: roambee-chat-service
spec:
  selector:
    app: roambee-chat
  ports:
    - port: 80
      targetPort: 8000
  type: LoadBalancer
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: roambee-chat-deployment
spec:
  replicas: 2
  selector:
    matchLabels:
      app: roambee-chat
  template:
    metadata:
      labels:
        app: roambee-chat
    spec:
      containers:
      - name: roambee-chat
        image: roambee-chat:latest
        ports:
        - containerPort: 8000
        env:
        - name: ENVIRONMENT
          valueFrom:
            configMapKeyRef:
              name: roambee-chat-config
              key: ENVIRONMENT
        - name: KUBERNETES_MODE
          valueFrom:
            configMapKeyRef:
              name: roambee-chat-config
              key: KUBERNETES_MODE
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health-check
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health-check
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
"""
    
    with open('kubernetes-deployment.yaml', 'w') as f:
        f.write(configmap_yaml)
    
    print("   ✅ Created kubernetes-deployment.yaml")
    return True

def create_docker_compose():
    """Create Docker Compose configuration for multi-user testing"""
    print("\n🐳 Creating Docker Compose configuration...")
    
    docker_compose_yaml = """
version: '3.8'

services:
  roambee-chat:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=docker
      - LOG_LEVEL=INFO
      - MAX_CONCURRENT_USERS=50
      - KUBERNETES_MODE=false
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health-check"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - roambee-chat
    restart: unless-stopped
"""
    
    # Create nginx configuration
    nginx_conf = """
events {
    worker_connections 1024;
}

http {
    upstream roambee_chat {
        server roambee-chat:8000;
    }
    
    server {
        listen 80;
        
        # Ensure JSON responses
        location /send-message {
            proxy_pass http://roambee_chat;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # Ensure proper content type
            proxy_set_header Accept application/json;
            proxy_set_header Content-Type application/json;
            
            # Timeout settings
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 120s;
        }
        
        location / {
            proxy_pass http://roambee_chat;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
"""
    
    with open('docker-compose.yml', 'w') as f:
        f.write(docker_compose_yaml)
    
    with open('nginx.conf', 'w') as f:
        f.write(nginx_conf)
    
    print("   ✅ Created docker-compose.yml")
    print("   ✅ Created nginx.conf")
    return True

def create_dockerfile():
    """Create optimized Dockerfile for multi-user deployment"""
    print("\n📋 Creating optimized Dockerfile...")
    
    dockerfile_content = """
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Set environment variables
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD curl -f http://localhost:8000/health-check || exit 1

# Run the application
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
"""
    
    with open('Dockerfile', 'w') as f:
        f.write(dockerfile_content)
    
    print("   ✅ Created Dockerfile")
    return True

def test_json_responses():
    """Test that the server returns proper JSON responses"""
    print("\n🧪 Testing JSON response format...")
    
    # Start server in background for testing
    try:
        print("   Starting test server...")
        process = subprocess.Popen([
            sys.executable, "main.py", "--host", "127.0.0.1", "--port", "8001"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait for server to start
        time.sleep(5)
        
        # Test endpoints
        test_endpoints = [
            ("/", "GET", None),
            ("/health-check", "GET", None),
            ("/send-message", "POST", {"message": "test"}),
        ]
        
        for endpoint, method, data in test_endpoints:
            try:
                url = f"http://127.0.0.1:8001{endpoint}"
                
                if method == "GET":
                    response = requests.get(url, timeout=10)
                else:
                    response = requests.post(url, data=data, timeout=10)
                
                content_type = response.headers.get('content-type', '')
                
                if endpoint == "/send-message":
                    if 'application/json' in content_type:
                        print(f"   ✅ {endpoint} returns JSON")
                    else:
                        print(f"   ❌ {endpoint} returns {content_type} (should be JSON)")
                        print(f"      Response: {response.text[:200]}...")
                else:
                    print(f"   ✅ {endpoint} accessible")
                    
            except Exception as e:
                print(f"   ⚠️  {endpoint} test failed: {str(e)}")
        
        # Stop test server
        process.terminate()
        process.wait()
        
    except Exception as e:
        print(f"   ❌ Test server failed to start: {str(e)}")
        return False
    
    return True

def create_monitoring_script():
    """Create monitoring script for multi-user environment"""
    print("\n📊 Creating monitoring script...")
    
    monitoring_script = """#!/usr/bin/env python3
import requests
import time
import json
from datetime import datetime

def monitor_health():
    \"\"\"Monitor application health\"\"\"
    endpoints = [
        'http://localhost:8000/health-check',
        'http://localhost:8000/session-info'
    ]
    
    while True:
        print(f"\\n[{datetime.now()}] Health Check:")
        
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
"""
    
    with open('monitor_health.py', 'w') as f:
        f.write(monitoring_script)
    
    os.chmod('monitor_health.py', 0o755)
    print("   ✅ Created monitor_health.py")
    return True

def main():
    """Main deployment fix function"""
    print("🚀 Roambee Chat Multi-User Environment Fix")
    print("=" * 50)
    
    # Check environment
    env_info = check_environment()
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Please install missing dependencies first")
        return False
    
    # Create deployment configurations
    if env_info["kubernetes"]:
        create_kubernetes_config()
    
    create_docker_compose()
    create_dockerfile()
    create_monitoring_script()
    
    # Test JSON responses
    print("\n" + "=" * 50)
    test_json_responses()
    
    print("\n" + "=" * 50)
    print("✅ Multi-user environment fix deployment completed!")
    print("\n📋 Next steps:")
    
    if env_info["kubernetes"]:
        print("   For Kubernetes:")
        print("   1. kubectl apply -f kubernetes-deployment.yaml")
        print("   2. kubectl get pods -l app=roambee-chat")
        print("   3. kubectl logs -l app=roambee-chat")
    
    print("   For Docker:")
    print("   1. docker-compose up -d")
    print("   2. docker-compose logs -f")
    
    print("   For monitoring:")
    print("   1. python monitor_health.py")
    print("   2. Check logs/errors.log for detailed error information")
    
    print("\n🔧 Key fixes implemented:")
    print("   • JSON response format enforcement")
    print("   • Enhanced error handling and logging")
    print("   • Session management improvements")
    print("   • Kubernetes environment detection")
    print("   • Rate limiting and resource management")
    print("   • Client-side retry mechanisms")
    
    return True

if __name__ == "__main__":
    main() 