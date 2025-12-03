# Redis Cache Setup Guide

## Prerequisites

1. **Install Redis** (if not already installed):

```bash
# macOS (using Homebrew)
brew install redis

# Start Redis server
brew services start redis

# Or run manually
redis-server
```

2. **Install Python dependencies**:

```bash
cd backend
pip install -r requirements.txt
```

## Configuration

1. **Update `.env` file** with Redis settings:

```bash
# Redis Cache (for answer and news caching)
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=  # Leave empty if no auth
```

2. **Verify Redis is running**:

```bash
redis-cli ping
# Should return: PONG
```

## Usage

### Start the Backend

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Monitor Cache

Visit `http://localhost:8000/api/cache/stats` to see:
- Total cached keys
- Answer cache count
- News cache count  
- Map cache count
- Memory usage

### Test Caching

1. **First request** (cache MISS):
```bash
curl -X POST http://localhost:8000/api/v1/mains-answer/generate \
  -H "Content-Type: application/json" \
  -d '{"question": "Discuss climate change impacts on Indian agriculture", "word_count": 350}'
```

2. **Second request** (cache HIT - instant response):
```bash
# Same question - should return in ~50ms
curl -X POST http://localhost:8000/api/v1/mains-answer/generate \
  -H "Content-Type: application/json" \
  -d '{"question": "Discuss climate change impacts on Indian agriculture", "word_count": 350}'
```

Check logs for `[CACHE HIT]` or `[CACHE MISS]` messages.

### Rate Limiting

Mains answer endpoint is limited to **20 requests per hour per IP**.

Exceeding this will return HTTP 429 (Too Many Requests).

## Cache Management

### View all cache keys:
```bash
redis-cli KEYS "study_buddy:*"
```

### Clear all cache:
```bash
redis-cli FLUSHDB
```

### Clear specific namespace:
```bash
# Clear all answer cache
redis-cli KEYS "study_buddy:answer:*" | xargs redis-cli DEL

# Clear all news cache
redis-cli KEYS "study_buddy:news:*" | xargs redis-cli DEL
```

## Troubleshooting

### Redis not running
```bash
# Check if Redis is running
redis-cli ping

# If not, start it
brew services start redis
```

### Cache not working
- Check `REDIS_ENABLED=true` in `.env`
- Verify Redis connection in backend logs: `✅ Redis connected`
- If disabled, logs show: `⚠️  Cache disabled (Redis not available)`

### Performance

**Cache Hit Rate** (expected):
- Answer cache: 40-60% (repeated questions)
- News cache: 70-80% (similar topics)
- Map cache: 90%+ (standard geography)

**Response Time** (typical):
- Cache HIT: ~50ms
- Cache MISS: ~7-10 seconds (full generation)
