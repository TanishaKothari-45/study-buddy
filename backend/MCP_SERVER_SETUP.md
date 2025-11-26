# MCP Current Affairs Server Setup

## Overview
The MCP (Model Context Protocol) server provides current affairs fetching functionality using multiple news API providers (GNews, NewsAPI, TheNewsAPI).

## Prerequisites

### Python Version
⚠️ **IMPORTANT**: The `mcp` package requires **Python 3.10 or higher**. 

Your current venv uses Python 3.9. You have two options:

1. **Upgrade Python in venv** (recommended):
   ```bash
   # Create new venv with Python 3.10+
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r backend/requirements.txt
   pip install mcp httpx
   ```

2. **Use system Python 3.10+** (if available):
   ```bash
   python3.10 backend/mcp_current_affairs_server.py
   ```

### Dependencies
```bash
pip install mcp httpx
```

## Configuration

### 1. Environment Variables
Add to your `.env` file:
```bash
GNEWS_API_KEY=your_gnews_api_key_here
# Optional - for other providers:
NEWS_API_KEY=your_newsapi_key
THENEWSAPI_KEY=your_thenewsapi_key
```

### 2. MCP Config File
The `mcp_config.json` file is already created at the project root. Update the path if needed:
```json
{
  "mcpServers": {
    "current-affairs": {
      "command": "python",
      "args": [
        "/Users/tanishakothari/Documents/Personal/study-buddy/backend/mcp_current_affairs_server.py"
      ],
      "env": {
        "GNEWS_API_KEY": "${GNEWS_API_KEY}"
      }
    }
  }
}
```

## Testing

### Option 1: Direct Test (No MCP Protocol)
Test the server functionality directly:
```bash
cd backend
python test_mcp_server.py "climate change India"
```

### Option 2: Full MCP Server
Run as MCP server (requires MCP client):
```bash
python backend/mcp_current_affairs_server.py
```

## API Providers

The server supports three providers (auto-selects based on available API keys):

1. **GNews.io** - Primary (requires `GNEWS_API_KEY`)
2. **NewsAPI.org** - Alternative (requires `NEWS_API_KEY`)
3. **TheNewsAPI.com** - Alternative (requires `THENEWSAPI_KEY`)

## Features

- ✅ Multiple news API providers with fallback
- ✅ Caching (1 hour TTL)
- ✅ Time range filtering (day, week, month, 3months, year)
- ✅ Region filtering (India, US, UK, etc.)
- ✅ Structured response with articles, summaries, dates, sources
- ✅ Key facts extraction
- ✅ Potential questions generation

## Integration with Existing Code

The MCP server can be used alongside the existing `web_searcher.py`:
- `web_searcher.py` - Uses SerpAPI/HTML fallback for general web search
- `mcp_current_affairs_server.py` - Uses news APIs for structured current affairs

Both can be used together for comprehensive current affairs fetching.

