"""
worker_entrypoint.py

Cloud Run Worker Entrypoint with HTTP Health Check.
Runs a minimal HTTP server for health checks alongside the Arq worker.

Usage:
    python -m app.worker_entrypoint
"""

import logging
import os
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for health checks."""
    
    def do_GET(self):
        """Respond 200 OK to any GET request (health check)."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK - Worker healthy')
    
    def log_message(self, format, *args):
        """Suppress HTTP access logs for cleaner output."""
        pass


def start_health_server(port: int) -> HTTPServer:
    """Start the health check HTTP server in a background thread."""
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"✅ Health check server started on port {port}")
    return server


def main():
    """Main entrypoint: Start health server, then run Arq worker."""
    # Import here to avoid circular imports and ensure proper initialization
    from arq import run_worker
    from app.worker import WorkerSettings
    
    # Get port from environment (Cloud Run sets PORT)
    port = int(os.environ.get('PORT', 8001))
    
    logger.info("=" * 50)
    logger.info("🔧 Study Buddy Worker - Cloud Run Entrypoint")
    logger.info("=" * 50)
    
    # Start health check server (runs in background thread)
    health_server = start_health_server(port)
    
    # Handle shutdown gracefully
    def signal_handler(sig, frame):
        logger.info(f"📛 Received signal {sig}, initiating shutdown...")
        health_server.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run Arq worker - this is SYNCHRONOUS and manages its own event loop
    # Do NOT wrap in asyncio.run() as arq handles its own loop
    try:
        logger.info("🚀 Starting Arq worker...")
        run_worker(WorkerSettings)
    except KeyboardInterrupt:
        logger.info("🛑 Worker interrupted")
    except Exception as e:
        logger.error(f"❌ Worker error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        health_server.shutdown()
        logger.info("👋 Worker shutdown complete")


if __name__ == "__main__":
    main()
