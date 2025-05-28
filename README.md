# Roambee MCP Chatbot Client

<div align="center">
  
![Roambee Logo](https://www.roambee.com/wp-content/uploads/2023/10/Roambee-Logo-Dark-Theme-Without-Background.png)

**Intelligent Supply Chain Visibility Platform**

[![Website](https://img.shields.io/badge/Website-roambee.com-blue?style=flat-square)](https://roambee.com)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Roambee-0077B5?style=flat-square&logo=linkedin)](https://www.linkedin.com/company/roambee/)
[![Twitter](https://img.shields.io/badge/Twitter-@Roambee-1DA1F2?style=flat-square&logo=twitter)](https://twitter.com/roam_bee)
[![YouTube](https://img.shields.io/badge/YouTube-Roambee-FF0000?style=flat-square&logo=youtube)](https://www.youtube.com/c/roambee)

</div>

## 🤖 About

The **Roambee MCP Chatbot Client** is an intelligent conversational interface that leverages the **Model Context Protocol (MCP)** to provide seamless access to Roambee's supply chain visibility tools and data. Built with FastAPI and modern web technologies, this chatbot enables users to interact with Roambee's platform through natural language conversations.

## ✨ Features

### 🚀 **Core Capabilities**
- **Dual AI Integration**: OpenAI GPT models + Roambee MCP tools
- **Real-time Validation**: Live API key validation for both OpenAI and Roambee
- **Session Management**: Secure session handling with automatic cleanup
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile

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

- **Python 3.8+**
- **OpenAI API Key** - [Get yours here](https://platform.openai.com/api-keys)
- **Roambee API Key** - Contact [Roambee Sales](https://roambee.com/contact-us/)

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/roambee/rb-mcp-demo.git
cd rb-mcp-demo
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment (Optional)
Create a `.env` file in the project root:
```env
HOST=localhost
PORT=4444
SECRET_KEY=your-secret-key-for-sessions
```

### 4. Start the Server
```bash
python main.py
```

### 5. Access the Application
Open your browser and navigate to: **http://localhost:4444**

## 🔐 API Key Configuration

### Initial Setup
1. **Navigate** to the configuration page (automatically shown on first visit)
2. **Enter your OpenAI API Key** (starts with `sk-`)
3. **Enter your Roambee API Key** (provided by Roambee team)
4. **Click Proceed** - both keys will be validated in real-time
5. **Start Chatting** - you'll be redirected to the chat interface

## 💬 Usage Examples

### Basic Queries
```
User: "What is my current inventory status?"
Bot: [Uses Roambee MCP tools to fetch real inventory data]

User: "Show me shipments delayed by more than 2 days"
Bot: [Queries Roambee API through MCP tools]

User: "Explain supply chain visibility best practices"
Bot: [Uses OpenAI when no specific Roambee tool is needed]
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │   FastAPI        │    │   External APIs │
│   (Chat UI)     │◄──►│   Backend        │◄──►│                 │
│                 │    │                  │    │  • OpenAI API   │
│  • React-like   │    │  • Session Mgmt  │    │  • Roambee API  │
│  • Responsive   │    │  • MCP Client    │    │  • MCP Server   │
│  • Themes       │    │  • AutoGen       │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📁 Project Structure

```
rb-mcp-demo/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── .env                   # Environment configuration (optional)
├── templates/             # HTML templates
│   ├── config.html        # API key configuration page
│   └── chat.html          # Main chat interface
└── static/               # Static assets
    ├── css/              # Stylesheets
    │   ├── config.css    # Configuration page styles
    │   └── chat.css      # Chat interface styles
    └── js/               # JavaScript files
        ├── config.js     # Configuration page logic
        └── chat.js       # Chat interface logic
```

## 🔧 Configuration Options

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `localhost` | Server host address |
| `PORT` | `4444` | Server port number |
| `SECRET_KEY` | Auto-generated | Session encryption key |

## 🔍 Troubleshooting

### Common Issues

**Q: "Invalid API key" error during setup**
- Verify your OpenAI key starts with `sk-`
- Confirm your Roambee API key is active
- Check network connectivity

**Q: MCP connection fails**
- Ensure Roambee API key has MCP access permissions
- Verify the MCP server URL is accessible
- Check firewall/proxy settings

**Q: Chat responses are slow**
- OpenAI API might be experiencing high load
- MCP server tools may have longer processing times
- Check your internet connection stability

### Getting Help
- **Documentation**: [Roambee Developer Portal](https://developers.roambee.com)
- **Support**: [support@roambee.com](mailto:support@roambee.com)
- **Community**: [Roambee LinkedIn Group](https://www.linkedin.com/company/roambee/)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

We welcome contributions! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting pull requests.

## 📞 Contact & Support

<div align="center">

### 🌐 **Connect with Roambee**

[![Website](https://img.shields.io/badge/🌐_Website-roambee.com-blue?style=for-the-badge)](https://roambee.com)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/roambee/)
[![Twitter](https://img.shields.io/badge/Twitter-1DA1F2?style=for-the-badge&logo=twitter&logoColor=white)](https://twitter.com/roambee)
[![YouTube](https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/c/roambee)

**📧 Email**: [info@roambee.com](mailto:info@roambee.com)  
**📞 Phone**: +1 (408) 933-3303  
**📍 Address**: Santa Clara, CA, USA

</div>

---

<div align="center">
  <sub>Built with ❤️ by the Roambee Team</sub>
</div>