# MCP Current Affairs Test Output (v2)

**Topic:** why forest fires increasing per year
**Started:** 2025-12-04T16:06:54.734375


============================================================
## Step: 0. Starting Test
**Time:** 16:06:54
============================================================
```
Topic: why forest fires increasing per year
```


============================================================
## Step: 1. Keyword Extraction
**Time:** 16:06:54
============================================================
```
Calling OpenAI GPT-4o-mini...
```


============================================================
## Step: 1. Keywords Result
**Time:** 16:06:55
============================================================
```json
{
  "keywords": [
    "forest fires",
    "increasing",
    "causes",
    "environment",
    "climate change"
  ]
}
```


============================================================
## Step: 2. Search Queries
**Time:** 16:06:55
============================================================
```json
[
  "forest fires increasing India latest",
  "forest fires global report study data",
  "forest fires increasing government scheme policy OR local initiatives",
  "forest fires global solution measures"
]
```


============================================================
## Step: 3. Fetching Candidates
**Time:** 16:06:55
============================================================
```
10 per query × 4 queries = 40 max
```


============================================================
## Step: 3.1 Query: forest fires increasing India latest...
**Time:** 16:06:59
============================================================
```json
{
  "count": 3,
  "sample_titles": [
    "Forest Department to generate 5 crore mandates emp",
    "Why are Uttarakhand forests turning into unmanagea",
    "20% forest area lost to urbanisation in Pakistan"
  ]
}
```


============================================================
## Step: 3.2 Query: forest fires global report study data...
**Time:** 16:06:59
============================================================
```json
{
  "count": 3,
  "sample_titles": [
    "10-fold rise in intense forest fires in India from",
    "Despite an increase in forest fires, the Union gov",
    "Indonesia 2019 forest fire destruction far worse t"
  ]
}
```


============================================================
## Step: 3.3 Query: forest fires increasing government schem...
**Time:** 16:06:59
============================================================
```json
{
  "count": 3,
  "sample_titles": [
    "Drivers and solutions to Southeast Asia’s biodiver",
    "UPSC Insights SECURE SYNOPSIS : 3 October 2025",
    "UPSC CURRENT AFFAIRS – 16 October 2025"
  ]
}
```


============================================================
## Step: 3.4 Query: forest fires global solution measures...
**Time:** 16:06:59
============================================================
```json
{
  "count": 3,
  "sample_titles": [
    "How forest fires are aggravating flash floods in t",
    "Action needed to fight devastating heath fires, sa",
    "Farmers must stop the fires"
  ]
}
```


============================================================
## Step: 3. Total Fetched
**Time:** 16:06:59
============================================================
```
12
```


============================================================
## Step: 4. After Dedupe
**Time:** 16:06:59
============================================================
```json
{
  "count": 12,
  "removed": 0
}
```


============================================================
## Step: 5. Content Extraction
**Time:** 16:06:59
============================================================
```
Scraping top 10 if needed...
```


============================================================
## Step: 5. Content Stats
**Time:** 16:07:09
============================================================
```json
{
  "scraped": 10,
  "avg_content_len": 2071
}
```


============================================================
## Step: 6. Computing Relevance Scores
**Time:** 16:07:09
============================================================
```
Using embedding similarity...
```


============================================================
## Step: 6. Top 5 by Relevance
**Time:** 16:07:26
============================================================
```json
[
  {
    "title": "10-fold rise in intense forest fires in ",
    "score": 0.628
  },
  {
    "title": "How forest fires are aggravating flash f",
    "score": 0.503
  },
  {
    "title": "Despite an increase in forest fires, the",
    "score": 0.501
  },
  {
    "title": "Action needed to fight devastating heath",
    "score": 0.495
  },
  {
    "title": "Why are Uttarakhand forests turning into",
    "score": 0.491
  }
]
```


============================================================
## Step: 7. Relevance Filter
**Time:** 16:07:26
============================================================
```json
{
  "threshold": 0.4,
  "passed": 7,
  "dropped": 5
}
```


============================================================
## Step: 8. Time Filter (90 days + fallback)
**Time:** 16:07:26
============================================================
```json
{
  "total_kept": 3,
  "recent": 0,
  "old_filled": 3
}
```


============================================================
## Step: 9. Classification
**Time:** 16:07:26
============================================================
```json
{
  "article": 3
}
```


============================================================
## Step: 10. Processing Editorials (New Pipeline)
**Time:** 16:07:26
============================================================
```
Using quality scoring + recency boost...
```


============================================================
## Step: 10. Selection
**Time:** 16:07:54
============================================================
```json
{
  "articles_selected": 3,
  "articles": [
    {
      "title": "10-fold rise in intense forest fires in ",
      "query": 1,
      "relevance": 0.628
    },
    {
      "title": "How forest fires are aggravating flash f",
      "query": 3,
      "relevance": 0.503
    },
    {
      "title": "Despite an increase in forest fires, the",
      "query": 1,
      "relevance": 0.501
    }
  ],
  "editorial": null
}
```


============================================================
## Step: 11. Extracts for Summarization
**Time:** 16:07:54
============================================================
```json
{
  "article_lead_lengths": [
    500,
    500,
    500
  ],
  "editorial_extract_length": 0
}
```


============================================================
## Step: 11. Calling Summarizer
**Time:** 16:07:54
============================================================
```
Batch LLM call...
```


============================================================
## Step: 11. Summaries Generated
**Time:** 16:07:58
============================================================
```json
{
  "article_summaries": [
    "36 per cent of India’s forest cover is in zones vulnerable to intense forest fires. The frequency and intensity of these fires increased between 2000 and 2019, as per a study by the Council on Energy.",
    "Wildfires and flash floods are symptoms of climate change in the Himalayas. Experts link intense forest fires to the rise in flash floods over the past 20 years, describing this as a ‘vicious cycle’.",
    "Uttarakhand reported 205 forest fires in the last seven days and 88 active large fires on April 27. In the first three months of 2021, India lost 2.82 million hectares to forest fires, amounting to 61% of the total land affected."
  ],
  "editorial_summary": null
}
```


============================================================
## Step: 12. FINAL OUTPUT
**Time:** 16:07:58
============================================================
```json
{
  "current_affairs": [
    {
      "type": "article",
      "summary": "36 per cent of India’s forest cover is in zones vulnerable to intense forest fires. The frequency and intensity of these fires increased between 2000 and 2019, as per a study by the Council on Energy.",
      "source": "theprint.in",
      "url": "https://theprint.in/environment/10-fold-rise-in-intense-forest-fires-in-india-from-2000-to-2019-study-points-to-climate-change/907731/",
      "published_at": "2022-04-08T12:04:45.000000Z",
      "corroborated": false,
      "relevance_score": 0.628
    },
    {
      "type": "article",
      "summary": "Wildfires and flash floods are symptoms of climate change in the Himalayas. Experts link intense forest fires to the rise in flash floods over the past 20 years, describing this as a ‘vicious cycle’.",
      "source": "scroll.in",
      "url": "https://scroll.in/article/1042112/how-forest-fires-are-aggravating-flash-floods-in-the-himalayas",
      "published_at": "2023-01-20T08:00:01.000000Z",
      "corroborated": false,
      "relevance_score": 0.503
    },
    {
      "type": "article",
      "summary": "Uttarakhand reported 205 forest fires in the last seven days and 88 active large fires on April 27. In the first three months of 2021, India lost 2.82 million hectares to forest fires, amounting to 61% of the total land affected.",
      "source": "scroll.in",
      "url": "https://scroll.in/article/1022835/despite-an-increase-in-forest-fires-the-union-government-is-giving-states-less-funds-to-fight-them",
      "published_at": "2022-05-01T16:00:01.000000Z",
      "corroborated": false,
      "relevance_score": 0.501
    }
  ],
  "metadata": {
    "keywords": [
      "forest fires",
      "increasing",
      "causes",
      "environment",
      "climate change"
    ],
    "queries_used": [
      "forest fires increasing India latest",
      "forest fires global report study data",
      "forest fires increasing government scheme policy OR local initiatives",
      "forest fires global solution measures"
    ]
  }
}
```

