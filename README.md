# Roambee MCP Demo

<div align="center">
  
![Roambee Logo](https://www.roambee.com/wp-content/uploads/2023/10/Roambee-Logo-Dark-Theme-Without-Background.png)

**Intelligent Supply Chain Visibility Platform**

[![Website](https://img.shields.io/badge/Website-roambee.com-blue?style=flat-square)](https://roambee.com)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Roambee-0077B5?style=flat-square&logo=linkedin)](https://www.linkedin.com/company/roambee/)
[![Twitter](https://img.shields.io/badge/Twitter-@Roambee-1DA1F2?style=flat-square&logo=twitter)](https://twitter.com/roam_bee)
[![YouTube](https://img.shields.io/badge/YouTube-Roambee-FF0000?style=flat-square&logo=youtube)](https://www.youtube.com/c/roambee)

</div>

## 🤖 About

The **Roambee MCP Demo** is an intelligent conversational interface that leverages the **Roambee MCP (Model Context Protocol) Server https://mcp-server.roambee.com/sse** to provide seamless access to Roambee's supply chain visibility tools and data. Built with FastAPI and modern web technologies, this MCP demo application enables users to interact with Roambee's platform through natural language conversations.

## ✨ Features

### 🚀 **Core Capabilities**
- **Dual AI Integration**: OpenAI GPT models + Roambee MCP tools
- **Real-time Validation**: Live API key validation for both OpenAI and Roambee
- **Session Management**: Secure session handling with automatic cleanup
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile
- **Structured Logging**: Comprehensive logging with configurable levels
- **Command Line Configuration**: Flexible host/port settings via CLI arguments

### 🔧 **MCP Integration**
- **Server-Sent Events (SSE)**: Real-time connection to Roambee MCP server
- **Tool Discovery**: Automatic detection and registration of available Roambee tools
- **AutoGen Agents**: Intelligent agent system for complex query handling
- **Fallback Support**: Graceful degradation to OpenAI when MCP tools are unavailable

### 🎨 **User Experience**
- **Chat Interface**: Familiar and intuitive chat experience
- **Dark/Light Themes**: Customizable appearance with system preference detection
- **Chat History**: Persistent conversation history with sidebar navigation
- **Settings Panel**: Easy configuration and API key management

## 📋 Prerequisites

- **Python 3.8+** or **Docker**
- **OpenAI API Key** - [Get yours here](https://platform.openai.com/api-keys)
- **Roambee API Key** - Contact [Roambee Sales](https://roambee.com/contact-us/)

## 🚀 Quick Start

### Option 1: Docker (Recommended)

#### Using Docker directly
```bash
# Build the image
docker build -t roambee-mcp-chatbot .

# Run with custom settings and debug logging
docker run -p 3000:3000 \
  -v $(pwd)/logs:/app/logs \
  roambee-mcp-chatbot \
  --host 0.0.0.0 --port 3000 --log-level DEBUG
```

### Option 2: Local Python Installation

#### 1. Clone the Repository
```bash
git clone https://github.com/roambee/rb-mcp-demo.git
cd rb-mcp-demo
```

#### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

#### 3. Start the Server
```bash
python main.py --host 0.0.0.0 --port 3000 --log-level DEBUG
```

### 4. Access the Application
Open your browser and navigate to: **http://localhost:3000** (or your custom port)

## 🔐 API Key Configuration

### Initial Setup
1. **Navigate** to the configuration page (automatically shown on first visit)
2. **Enter your OpenAI API Key** (starts with `sk-`)
3. **Enter your Roambee API Key** (provided by Roambee team)
4. **Click Proceed** - both keys will be validated in real-time
5. **Start Chatting** - you'll be redirected to the chat interface

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌───────────────────────┐
│   Frontend      │    │   FastAPI        │    │   External APIs       │
│   (Chat UI)     │◄──►│   Backend        │◄──►│                       │
│                 │    │                  │    │  • OpenAI API         │
│  • React-like   │    │  • Session Mgmt  │    │  • Roambee API        │
│  • Responsive   │    │  • MCP Client    │    │  • Roambee MCP Server │
│  • Themes       │    │  • AutoGen       │    │                       │
└─────────────────┘    └──────────────────┘    └───────────────────────┘
```

## 🔍 Troubleshooting

### Common Issues

**Q: "Invalid API key" error during setup**
- Verify your OpenAI key starts with `sk-`
- Confirm your Roambee API key is active
- Check network connectivity

**Q: Chat responses are slow**
- OpenAI API might be experiencing high load
- MCP server tools may have longer processing times
- Check your internet connection stability

**Q: Docker container won't start**
- Ensure Docker is running
- Check if port 3000 is already in use: `lsof -i :3000`
- Verify Docker has sufficient resources allocated

**Q: Port conflicts when running multiple containers**
- Use different external ports: `docker run -p 8080:8080` vs `docker run -p 9000:9000`
- Check what ports are in use: `docker ps` or `lsof -i :PORT`
- Update both the `-p` flag and `--port` argument to match

**Q: Can't access application from outside Docker host**
- Use `--host 0.0.0.0` instead of `localhost` or `127.0.0.1`
- Ensure firewall allows the specified port
- Check Docker port mapping: `-p HOST_PORT:CONTAINER_PORT`

### Getting Help
- **Support**: [support@roambee.com](mailto:support@roambee.com)
- **Community**: [Roambee LinkedIn Group](https://www.linkedin.com/company/roambee/)
- **Endpoint**: `http://localhost:3000/docs`

## 📞 Contact & Support

<div align="center">

### 🌐 **Connect with Roambee**

[![Website](https://img.shields.io/badge/🌐_Website-roambee.com-blue?style=for-the-badge)](https://roambee.com)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/roambee/)
[![Twitter](https://img.shields.io/badge/Twitter-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white)](https://twitter.com/roam_bee)
[![YouTube](https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/c/roambee)

**📧 Email**: [info@roambee.com](mailto:support@roambee.com)  
**📞 Phone**: +1 (408) 663 6655
**📍 Address**: 3120 De La Cruz Blvd Suite 210 Santa Clara, California 95054, USA

</div>

---

<div align="center">
  <sub>Built with ❤️ by the Roambee Team</sub>
</div>