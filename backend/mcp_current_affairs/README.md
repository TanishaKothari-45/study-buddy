# MCP Current Affairs - Modular Architecture

## Overview
Modular implementation of the Current Affairs MCP server with intelligent summarization, article classification, and editorial extraction.

## Directory Structure

```
mcp_current_affairs/
│
├── mcp_current_affairs_server.py        # Main MCP server (exposes tools)
├── config.py                            # Configuration and constants
├── __init__.py                          # Package initialization
│
├── fetcher/                             # News fetching components
│   ├── __init__.py
│   ├── news_fetcher.py                  # GNews + NewsAPI + TheNewsAPI
│   ├── editorial_rss.py                 # RSS feeds (Indian Express, Hindu, LiveMint)
│   └── utils.py                         # URL normalization, deduplication
│
├── processing/                          # Article processing
│   ├── __init__.py
│   ├── classifier.py                    # Article type detection + topic scoring
│   ├── selector.py                      # Select best 3 articles + 1 editorial
│   ├── summary_builder.py               # One-liners and editorial extraction
│   └── cache.py                         # Redis/local caching
│
└── llm/                                 # LLM operations
    ├── __init__.py
    ├── keyword_parser.py                # Topic → keywords extraction
    ├── summarizer.py                    # Intelligent summarization
    └── prompts.py                       # Prompt templates
```

## Features

### 🔍 Intelligent Keyword Extraction
- LLM-based topic parsing
- Extracts main topic, sub-topics, and optimized search queries
- Fallback parser for offline mode

### 📰 Multi-Source Fetching
- **News APIs**: NewsAPI, GNews, TheNewsAPI
- **RSS Feeds**: Indian Express, The Hindu, LiveMint editorials
- Concurrent fetching with rate limiting

### 🎯 Smart Article Selection
- Classifies articles as news/editorial/analysis
- Calculates topic relevance scores
- Selects best 3 articles + 1 editorial

### 🤖 LLM-Based Summarization
- Generates coherent 40-50 word summaries
- Handles different article types (news, editorial, analysis)
- Batch processing for efficiency
- Extracts conclusions from editorials

### 💾 Intelligent Caching
- Redis support with local fallback
- 24-hour cache for keywords
- 7-day cache for summaries
- Automatic cache expiration

## Usage

### Running the MCP Server

```bash
cd backend
python3 mcp_current_affairs/mcp_current_affairs_server.py
```

### Using in Code

```python
from mcp_current_affairs import (
    NewsFetcher,
    ArticleSelector,
    Summarizer,
    KeywordParser,
)

# Initialize components
fetcher = NewsFetcher()
selector = ArticleSelector()
summarizer = Summarizer(gemini_client)

# Fetch and process
results = await fetcher.fetch_articles("climate change India")
selection = selector.select_best_articles(results["articles"])
summaries = await summarizer.summarize_batch(selection["articles"])
```

### MCP Tool

```json
{
  "name": "fetch_current_affairs",
  "arguments": {
    "topic": "Discuss the impact of climate change on Indian agriculture",
    "time_range": "3months"
  }
}
```

**Returns:**
- 3 best articles with intelligent summaries
- 1 editorial with extracted insights
- Context bullets ready for LLM consumption

## Configuration

Edit `config.py` to customize:

- **API Keys**: NEWS_API_KEY, GNEWS_API_KEY, THENEWSAPI_KEY
- **Cache Settings**: TTLs, Redis connection
- **Selection Limits**: MAX_ARTICLES, MAX_EDITORIALS
- **Batch Sizes**: BATCH_SIZE, MAX_CONCURRENT_BATCHES

## Dependencies

```bash
pip install httpx feedparser mcp redis
```

## Architecture Benefits

✅ **Modular**: Each component has a single responsibility  
✅ **Testable**: Easy to unit test individual modules  
✅ **Maintainable**: Clear separation of concerns  
✅ **Extensible**: Add new providers or processors easily  
✅ **Cacheable**: Intelligent caching reduces API calls  
✅ **Concurrent**: Parallel fetching and processing  

## Next Steps

1. Drop your code into the respective files
2. Review and adjust the implementations
3. Test with sample topics
4. Integrate with existing answer generation flow
