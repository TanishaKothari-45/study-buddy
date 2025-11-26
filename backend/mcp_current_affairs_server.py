#!/usr/bin/env python3
"""
Current Affairs MCP Server (Python)
Fetches recent news and current affairs for mock test generation
Strategy: Fetch Broad + Filter Local for guaranteed results
"""

import asyncio
import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import quote
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

# Load environment variables from .env file
project_root = Path(__file__).resolve().parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}")
else:
    print(f"⚠️ .env file not found at: {env_path}")

# API Configuration
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY", "")
THENEWSAPI_KEY = os.getenv("THENEWSAPI_KEY", "")

# Log which API keys are available
if GNEWS_API_KEY:
    print(f"✅ GNEWS_API_KEY found (length: {len(GNEWS_API_KEY)})")
if NEWS_API_KEY:
    print(f"✅ NEWS_API_KEY found (length: {len(NEWS_API_KEY)})")
if THENEWSAPI_KEY:
    print(f"✅ THENEWSAPI_KEY found (length: {len(THENEWSAPI_KEY)})")

# Simple in-memory cache
cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 3600  # 1 hour in seconds


class CurrentAffairsMCPServer:
    def __init__(self):
        self.server = Server("current-affairs-mcp")
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.setup_handlers()

    def setup_handlers(self):
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            return [
                Tool(
                    name="fetch_current_affairs",
                    description=(
                        "Fetch recent current affairs and news articles based on a topic context. "
                        "Returns structured data suitable for mock test generation including headlines, "
                        "summaries, dates, and sources."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": (
                                    "The topic or subject area for current affairs "
                                    "(e.g., 'climate change', 'Indian politics', 'technology', 'sports')"
                                ),
                            },
                            "time_range": {
                                "type": "string",
                                "enum": ["day", "week", "month", "3months", "year"],
                                "description": "Time range for news articles (default: 3months)",
                                "default": "3months",
                            },
                            "region": {
                                "type": "string",
                                "description": "Geographic region to focus on (e.g., 'India', 'global', 'Asia')",
                            },
                            "count": {
                                "type": "number",
                                "description": "Number of articles to fetch (default: 10, max: 100)",
                                "default": 10,
                            },
                            "api_provider": {
                                "type": "string",
                                "enum": ["newsapi", "gnews", "thenewsapi"],
                                "description": "News API provider to use (default: auto-selects best available)",
                            },
                        },
                        "required": ["topic"],
                    },
                ),
                Tool(
                    name="fetch_diversified_current_affairs",
                    description=(
                        "Fetch diversified current affairs covering latest issues, government initiatives, "
                        "policies, and developments both in India and globally for a given topic. "
                        "Uses 'Fetch Broad + Filter Local' strategy for guaranteed results. "
                        "Returns categorized articles perfect for comprehensive mock test preparation."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": (
                                    "The main topic or domain (e.g., 'environment', 'economy', 'technology', "
                                    "'healthcare', 'education', 'defence')"
                                ),
                            },
                            "time_range": {
                                "type": "string",
                                "enum": ["day", "week", "month", "3months", "year"],
                                "description": "Time range for news articles (default: 3months)",
                                "default": "3months",
                            },
                            "total_articles": {
                                "type": "number",
                                "description": "Total articles to fetch before filtering (default: 50, max: 100)",
                                "default": 50,
                            },
                            "api_provider": {
                                "type": "string",
                                "enum": ["newsapi", "gnews", "thenewsapi"],
                                "description": "News API provider to use (default: auto-selects best available)",
                            },
                        },
                        "required": ["topic"],
                    },
                ),
                Tool(
                    name="get_topic_timeline",
                    description=(
                        "Get a chronological timeline of major events for a specific topic. "
                        "Useful for understanding the progression of events."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "The topic to get timeline for",
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format",
                            },
                        },
                        "required": ["topic"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> List[TextContent]:
            try:
                if name == "fetch_current_affairs":
                    result = await self.fetch_current_affairs(
                        topic=arguments.get("topic"),
                        time_range=arguments.get("time_range", "3months"),
                        region=arguments.get("region"),
                        count=arguments.get("count", 10),
                        api_provider=arguments.get("api_provider"),
                    )
                elif name == "fetch_diversified_current_affairs":
                    result = await self.fetch_diversified_current_affairs(
                        topic=arguments.get("topic"),
                        time_range=arguments.get("time_range", "3months"),
                        total_articles=arguments.get("total_articles", 50),
                        api_provider=arguments.get("api_provider"),
                    )
                elif name == "get_topic_timeline":
                    result = await self.get_topic_timeline(
                        topic=arguments.get("topic"),
                        start_date=arguments.get("start_date"),
                        end_date=arguments.get("end_date"),
                    )
                else:
                    raise ValueError(f"Unknown tool: {name}")

                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            except Exception as e:
                return [TextContent(type="text", text=f"Error: {str(e)}")]

    async def fetch_current_affairs(
        self,
        topic: str,
        time_range: str = "3months",
        region: Optional[str] = None,
        count: int = 10,
        api_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        cache_key = f"affairs_{topic}_{time_range}_{region}_{count}_{api_provider}"

        # Check cache
        if cache_key in cache:
            cached_data = cache[cache_key]
            if datetime.now().timestamp() - cached_data["timestamp"] < CACHE_TTL:
                return cached_data["data"]

        # Determine which API to use
        provider = api_provider or self.select_best_provider()

        # Fetch data based on provider
        if provider == "newsapi":
            result = await self.fetch_from_newsapi(topic, time_range, region, count)
        elif provider == "gnews":
            result = await self.fetch_from_gnews(topic, time_range, region, count)
        elif provider == "thenewsapi":
            result = await self.fetch_from_thenewsapi(topic, time_range, region, count)
        else:
            raise ValueError("No API provider available")

        # Cache the result
        cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}

        return result

    async def fetch_diversified_current_affairs(
        self,
        topic: str,
        time_range: str = "3months",
        total_articles: int = 50,
        api_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        NEW STRATEGY: Fetch Broad + Filter Local
        
        1. Fetch broad articles (e.g., "forest fires India", "forest fires global")
        2. Filter locally based on keywords to categorize
        3. Guaranteed results since broad searches always work
        """
        
        cache_key = f"diversified_v2_{topic}_{time_range}_{total_articles}_{api_provider}"

        # Check cache
        if cache_key in cache:
            cached_data = cache[cache_key]
            if datetime.now().timestamp() - cached_data["timestamp"] < CACHE_TTL:
                return cached_data["data"]

        provider = api_provider or self.select_best_provider()

        # STEP 1: Fetch broad articles from 3 simple searches
        all_articles = []
        search_queries = [
            {"query": f"{topic} India", "region": "India"},
            {"query": f"{topic} global", "region": "global"},
            {"query": f"{topic}", "region": None},  # General search
        ]

        print(f"📡 Fetching broad articles for: {topic}")
        
        for search_info in search_queries:
            try:
                # Calculate articles per query (distribute evenly)
                articles_per_query = max(10, total_articles // len(search_queries))
                
                if provider == "newsapi":
                    result = await self.fetch_from_newsapi(
                        search_info["query"], time_range, search_info["region"], articles_per_query
                    )
                elif provider == "gnews":
                    result = await self.fetch_from_gnews(
                        search_info["query"], time_range, search_info["region"], min(articles_per_query, 10)
                    )
                elif provider == "thenewsapi":
                    result = await self.fetch_from_thenewsapi(
                        search_info["query"], time_range, search_info["region"], articles_per_query
                    )
                else:
                    raise ValueError("No API provider available")

                # Add source query info to each article
                for article in result.get("articles", []):
                    article["source_query"] = search_info["query"]
                    article["source_region"] = search_info["region"]
                
                all_articles.extend(result.get("articles", []))
                
                print(f"  ✓ Fetched {len(result.get('articles', []))} articles for: {search_info['query']}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"  ✗ Error fetching {search_info['query']}: {e}")
                continue

        print(f"📚 Total articles fetched: {len(all_articles)}")

        # STEP 2: Filter and categorize locally based on keywords
        categories = {
            "india_issues": {
                "description": "Latest issues and challenges in India",
                "articles": [],
                "keywords": ["india", "indian", "delhi", "mumbai", "bengaluru", "challenge", "crisis", "problem", "issue", "concern"],
                "exclude_keywords": ["policy", "scheme", "initiative", "program", "government launch", "ministry"],
            },
            "global_issues": {
                "description": "Latest global issues and challenges",
                "articles": [],
                "keywords": ["global", "world", "international", "worldwide", "crisis", "challenge", "problem"],
                "exclude_keywords": ["india", "indian", "policy", "initiative", "agreement"],
            },
            "india_initiatives": {
                "description": "Government initiatives and policies in India",
                "articles": [],
                "keywords": ["india", "indian", "government", "policy", "scheme", "initiative", "program", "ministry", "launch", "announce", "bill", "act"],
                "exclude_keywords": [],
            },
            "global_initiatives": {
                "description": "International initiatives and policies",
                "articles": [],
                "keywords": ["global", "international", "UN", "WHO", "world", "treaty", "agreement", "summit", "conference", "initiative", "policy"],
                "exclude_keywords": ["india only"],  # Allow India in global context
            },
            "developments": {
                "description": "Recent developments and innovations",
                "articles": [],
                "keywords": ["breakthrough", "innovation", "development", "technology", "advance", "new", "discover", "research", "study"],
                "exclude_keywords": [],
            },
        }

        # Categorize articles
        print(f"🔍 Categorizing articles...")
        
        for article in all_articles:
            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()
            content = title + " " + summary
            
            # Track which categories match
            category_scores = {}
            
            for category_key, category_info in categories.items():
                score = 0
                
                # Check keyword matches
                for keyword in category_info["keywords"]:
                    if keyword in content:
                        score += 1
                
                # Check exclude keywords (reduce score)
                for exclude_keyword in category_info["exclude_keywords"]:
                    if exclude_keyword in content:
                        score -= 2
                
                if score > 0:
                    category_scores[category_key] = score
            
            # Assign to best matching category
            if category_scores:
                best_category = max(category_scores, key=category_scores.get)
                categories[best_category]["articles"].append(article)

        # STEP 3: Format results
        all_categories = {}
        for category_key, category_info in categories.items():
            all_categories[category_key] = {
                "description": category_info["description"],
                "articles": category_info["articles"],
                "count": len(category_info["articles"]),
            }
            print(f"  ✓ {category_key}: {len(category_info['articles'])} articles")

        # Calculate statistics
        total_categorized = sum(cat["count"] for cat in all_categories.values())
        india_articles = sum(
            cat["count"] 
            for cat_key, cat in all_categories.items() 
            if "india" in cat_key
        )
        global_articles = sum(
            cat["count"] 
            for cat_key, cat in all_categories.items() 
            if "global" in cat_key
        )

        result = {
            "topic": topic,
            "time_range": time_range,
            "provider": provider,
            "strategy": "Fetch Broad + Filter Local",
            "diversification_strategy": {
                "approach": "Fetched broad articles and filtered locally by keywords",
                "broad_searches": [sq["query"] for sq in search_queries],
                "categories": list(categories.keys()),
                "coverage": "India + Global + Initiatives + Issues + Developments",
            },
            "statistics": {
                "total_fetched": len(all_articles),
                "total_categorized": total_categorized,
                "india_focused": india_articles,
                "global_focused": global_articles,
                "categories_covered": len([cat for cat in all_categories.values() if cat["count"] > 0]),
            },
            "categories": all_categories,
            "metadata": {
                "fetched_at": datetime.now().isoformat(),
                "cache_key": cache_key,
            },
        }

        # Cache the result
        cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}

        return result

    async def get_topic_timeline(
        self,
        topic: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        cache_key = f"timeline_{topic}_{start_date}_{end_date}"

        # Check cache
        if cache_key in cache:
            cached_data = cache[cache_key]
            if datetime.now().timestamp() - cached_data["timestamp"] < CACHE_TTL:
                return cached_data["data"]

        date_range = f" from {start_date} to {end_date}" if start_date and end_date else ""
        search_query = f"{topic} timeline major events{date_range}"

        result = {
            "topic": topic,
            "date_range": {"start": start_date, "end": end_date},
            "query": search_query,
            "search_instructions": "Use web_search tool with the provided query to fetch timeline data",
            "response_format": {
                "events": [
                    {
                        "date": "Event date",
                        "title": "Event title",
                        "description": "Brief description",
                        "significance": "Why this event is important",
                        "related_topics": ["Related topic 1", "Related topic 2"],
                    }
                ],
                "summary": "Overall summary of developments during this time period",
            },
        }

        # Cache the result
        cache[cache_key] = {"data": result, "timestamp": datetime.now().timestamp()}

        return result

    def select_best_provider(self) -> str:
        """Select best available provider. Prefer TheNewsAPI > NewsAPI > GNews"""
        if THENEWSAPI_KEY:
            return "thenewsapi"
        if NEWS_API_KEY:
            return "newsapi"
        if GNEWS_API_KEY:
            return "gnews"
        raise ValueError(
            "No API key configured. Set NEWS_API_KEY, GNEWS_API_KEY, or THENEWSAPI_KEY environment variable."
        )

    async def fetch_from_newsapi(
        self, topic: str, time_range: str, region: Optional[str], count: int
    ) -> Dict[str, Any]:
        from_date = self.get_from_date(time_range)
        to_date = datetime.now().strftime("%Y-%m-%d")

        query = f"{topic} {region}" if region else topic
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q={quote(query)}&"
            f"from={from_date}&"
            f"to={to_date}&"
            f"pageSize={min(count, 100)}&"
            f"sortBy=publishedAt&"
            f"language=en&"
            f"apiKey={NEWS_API_KEY}"
        )

        response = await self.http_client.get(url)
        response.raise_for_status()
        data = response.json()

        return self.format_newsapi_response(data, topic, time_range)

    async def fetch_from_gnews(
        self, topic: str, time_range: str, region: Optional[str], count: int
    ) -> Dict[str, Any]:
        url = (
            f"https://gnews.io/api/v4/search?"
            f"q={quote(topic)}&"
            f"max={min(count, 10)}&"
            f"sortby=publishedAt&"
            f"lang=en&"
            f"apikey={GNEWS_API_KEY}"
        )

        if region:
            country_code = self.get_country_code(region)
            if country_code:
                url += f"&country={country_code}"

        response = await self.http_client.get(url)
        response.raise_for_status()
        data = response.json()

        return self.format_gnews_response(data, topic, time_range)

    async def fetch_from_thenewsapi(
        self, topic: str, time_range: str, region: Optional[str], count: int
    ) -> Dict[str, Any]:
        from_date = self.get_from_date(time_range)

        url = (
            f"https://api.thenewsapi.com/v1/news/all?"
            f"search={quote(topic)}&"
            f"limit={min(count, 100)}&"
            f"published_after={from_date}&"
            f"language=en&"
            f"api_token={THENEWSAPI_KEY}"
        )

        if region:
            locale = self.get_locale_code(region)
            if locale:
                url += f"&locale={locale}"

        response = await self.http_client.get(url)
        response.raise_for_status()
        data = response.json()

        return self.format_thenewsapi_response(data, topic, time_range)

    def format_newsapi_response(
        self, data: Dict[str, Any], topic: str, time_range: str
    ) -> Dict[str, Any]:
        articles = data.get("articles", [])
        return {
            "topic": topic,
            "time_range": time_range,
            "provider": "NewsAPI.org",
            "total_results": data.get("totalResults", 0),
            "articles": [
                {
                    "title": article.get("title"),
                    "summary": article.get("description"),
                    "content_preview": article.get("content", "")[:200] if article.get("content") else None,
                    "date": article.get("publishedAt"),
                    "source": article.get("source", {}).get("name"),
                    "url": article.get("url"),
                    "image_url": article.get("urlToImage"),
                    "author": article.get("author"),
                    "key_facts": self.extract_key_facts(article.get("description", "")),
                    "potential_questions": self.generate_questions(
                        article.get("title", ""), article.get("description", "")
                    ),
                }
                for article in articles
            ],
            "metadata": {
                "fetched_at": datetime.now().isoformat(),
                "query": topic,
            },
        }

    def format_gnews_response(
        self, data: Dict[str, Any], topic: str, time_range: str
    ) -> Dict[str, Any]:
        articles = data.get("articles", [])
        return {
            "topic": topic,
            "time_range": time_range,
            "provider": "GNews.io",
            "total_results": data.get("totalArticles", 0),
            "articles": [
                {
                    "title": article.get("title"),
                    "summary": article.get("description"),
                    "content_preview": article.get("content", "")[:200] if article.get("content") else None,
                    "date": article.get("publishedAt"),
                    "source": article.get("source", {}).get("name"),
                    "url": article.get("url"),
                    "image_url": article.get("image"),
                    "key_facts": self.extract_key_facts(article.get("description", "")),
                    "potential_questions": self.generate_questions(
                        article.get("title", ""), article.get("description", "")
                    ),
                }
                for article in articles
            ],
            "metadata": {
                "fetched_at": datetime.now().isoformat(),
                "query": topic,
            },
        }

    def format_thenewsapi_response(
        self, data: Dict[str, Any], topic: str, time_range: str
    ) -> Dict[str, Any]:
        articles = data.get("data", [])
        return {
            "topic": topic,
            "time_range": time_range,
            "provider": "TheNewsAPI.com",
            "total_results": data.get("meta", {}).get("found", 0),
            "articles": [
                {
                    "title": article.get("title"),
                    "summary": article.get("description"),
                    "content_preview": article.get("snippet", "")[:200] if article.get("snippet") else None,
                    "date": article.get("published_at"),
                    "source": article.get("source"),
                    "url": article.get("url"),
                    "image_url": article.get("image_url"),
                    "categories": article.get("categories"),
                    "key_facts": self.extract_key_facts(article.get("description", "")),
                    "potential_questions": self.generate_questions(
                        article.get("title", ""), article.get("description", "")
                    ),
                }
                for article in articles
            ],
            "metadata": {
                "fetched_at": datetime.now().isoformat(),
                "query": topic,
            },
        }

    @staticmethod
    def extract_key_facts(text: str) -> List[str]:
        if not text:
            return []
        # Simple fact extraction - split by sentences and take first 3
        sentences = [s.strip() + "." for s in text.split(".") if s.strip()]
        return sentences[:3]

    @staticmethod
    def generate_questions(title: str, description: str) -> List[str]:
        questions = []
        if title:
            questions.append(f'What is the main topic discussed in: "{title[:50]}..."?')
        if description and len(description) > 50:
            title_words = " ".join(title.split()[:3]) if title else "the topic"
            questions.append(
                f"According to recent reports, what developments have occurred regarding {title_words}?"
            )
        return questions[:2]

    @staticmethod
    def get_from_date(time_range: str) -> str:
        now = datetime.now()
        if time_range == "day":
            from_date = now - timedelta(days=1)
        elif time_range == "week":
            from_date = now - timedelta(weeks=1)
        elif time_range == "month":
            from_date = now - timedelta(days=30)
        elif time_range == "3months":
            from_date = now - timedelta(days=90)
        elif time_range == "year":
            from_date = now - timedelta(days=365)
        else:
            from_date = now - timedelta(days=90)  # Default to 3 months

        return from_date.strftime("%Y-%m-%d")

    @staticmethod
    def get_country_code(region: str) -> Optional[str]:
        mapping = {
            "india": "in",
            "us": "us",
            "usa": "us",
            "united states": "us",
            "uk": "gb",
            "united kingdom": "gb",
            "canada": "ca",
            "australia": "au",
            "global": "",
        }
        return mapping.get(region.lower())

    @staticmethod
    def get_locale_code(region: str) -> Optional[str]:
        mapping = {
            "india": "in",
            "us": "us",
            "usa": "us",
            "united states": "us",
            "uk": "gb",
            "united kingdom": "gb",
            "canada": "ca",
            "australia": "au",
        }
        return mapping.get(region.lower())

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())


async def main():
    server = CurrentAffairsMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())