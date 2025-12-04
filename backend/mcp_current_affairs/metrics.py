# metrics.py
"""
Simple metrics tracking for MCP Current Affairs server.
Tracks cache hits/misses, API failures, latencies, and source usage.
"""

import time
from typing import Dict, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class MCPMetrics:
    """Simple metrics tracker for the MCP server."""
    
    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # API metrics
    api_failures: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    api_latencies: list = field(default_factory=list)
    
    # Source usage
    sources_used: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Request metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Timing
    _start_time: float = field(default_factory=time.time)
    
    def record_cache_hit(self):
        self.cache_hits += 1
    
    def record_cache_miss(self):
        self.cache_misses += 1
    
    def record_api_failure(self, reason: str):
        self.api_failures[reason] += 1
    
    def record_api_latency(self, latency_ms: float):
        self.api_latencies.append(latency_ms)
        # Keep only last 100 for memory efficiency
        if len(self.api_latencies) > 100:
            self.api_latencies = self.api_latencies[-100:]
    
    def record_source_used(self, source: str):
        self.sources_used[source] += 1
    
    def record_request(self, success: bool):
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
    
    def get_avg_latency(self) -> float:
        if not self.api_latencies:
            return 0.0
        return sum(self.api_latencies) / len(self.api_latencies)
    
    def get_cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total
    
    def get_success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    def get_uptime_seconds(self) -> float:
        return time.time() - self._start_time
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        return {
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": f"{self.get_cache_hit_rate():.1%}"
            },
            "api": {
                "avg_latency_ms": round(self.get_avg_latency(), 1),
                "failures": dict(self.api_failures)
            },
            "sources": dict(self.sources_used),
            "requests": {
                "total": self.total_requests,
                "success_rate": f"{self.get_success_rate():.1%}"
            },
            "uptime_seconds": round(self.get_uptime_seconds(), 1)
        }
    
    def log_summary(self):
        """Print metrics summary to console."""
        summary = self.get_summary()
        print("\n📊 MCP Metrics Summary:")
        print(f"   Cache: {summary['cache']['hits']} hits, {summary['cache']['misses']} misses ({summary['cache']['hit_rate']})")
        print(f"   API Latency: {summary['api']['avg_latency_ms']}ms avg")
        print(f"   Sources: {dict(summary['sources'])}")
        print(f"   Requests: {summary['requests']['total']} total ({summary['requests']['success_rate']})")
        print(f"   Uptime: {summary['uptime_seconds']}s\n")


# Global metrics instance
metrics = MCPMetrics()
