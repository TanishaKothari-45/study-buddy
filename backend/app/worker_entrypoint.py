"""
worker_entrypoint.py

Cloud Run Worker Entrypoint with HTTP Health Check.
Runs a minimal HTTP server for health checks alongside the Arq worker.

IMPORTANT: Health check server MUST start BEFORE any heavy imports to ensure
Cloud Run can probe the container even if imports fail.

Usage:
    python -m app.worker_entrypoint
"""

import logging
import os
import signal
import sys
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Event

# Configure logging FIRST (before any other imports)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state for health check (thread-safe via Event)
_worker_ready = Event()
_startup_error = None
_startup_error_time = None


class HealthCheckHandler(BaseHTTPRequestHandler):
    """
    Minimal HTTP handler for health checks.
    
    Returns:
    - 200 OK: Worker is healthy and ready
    - 200 OK (starting): Worker is still initializing (within grace period)
    - 503 Service Unavailable: Worker failed to start
    """
    
    def do_GET(self):
        """Respond to health check requests."""
        global _startup_error, _startup_error_time
        
        if _worker_ready.is_set():
            # Worker is fully ready
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK - Worker healthy and ready')
        elif _startup_error:
            # Startup failed - but still return 200 for first 60 seconds
            # This gives Cloud Run time to see logs before killing container
            elapsed = time.time() - _startup_error_time if _startup_error_time else 0
            if elapsed < 60:
                # Grace period: return 200 so Cloud Run doesn't immediately kill us
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                error_msg = f'Starting (error occurred, logging): {_startup_error[:200]}'
                self.wfile.write(error_msg.encode('utf-8'))
            else:
                # After grace period, return 503 to trigger restart
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'FAILED: {_startup_error[:500]}'.encode('utf-8'))
        else:
            # Still starting up - return 200 to pass health checks
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK - Worker starting up...')
    
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
    """
    Main entrypoint: Start health server FIRST, then initialize worker.
    
    This ensures Cloud Run can always reach the health endpoint, even if
    the worker fails to initialize due to import errors or connection issues.
    """
    global _startup_error, _startup_error_time
    
    # Get port from environment (Cloud Run sets PORT=8080)
    port = int(os.environ.get('PORT', 8001))
    
    logger.info("=" * 60)
    logger.info("🔧 Study Buddy Worker - Cloud Run Entrypoint")
    logger.info("=" * 60)
    logger.info(f"📍 PORT: {port}")
    logger.info(f"📍 ENVIRONMENT: {os.environ.get('ENVIRONMENT', 'unknown')}")
    
    # ================================================================
    # STEP 1: Start health check server IMMEDIATELY
    # This MUST happen before any heavy imports to ensure Cloud Run
    # can reach the health endpoint even if imports fail
    # ================================================================
    health_server = start_health_server(port)
    logger.info("✅ Health check server is running - Cloud Run can now probe us")
    
    # Handle shutdown gracefully
    shutdown_requested = Event()
    
    def signal_handler(sig, frame):
        logger.info(f"📛 Received signal {sig}, initiating shutdown...")
        shutdown_requested.set()
        health_server.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # ================================================================
    # STEP 2: Import worker dependencies (may fail)
    # ================================================================
    logger.info("📦 Importing worker dependencies...")
    
    try:
        # These imports can fail if secrets/env vars are missing
        from arq import run_worker
        logger.info("  ✓ arq imported")
        
        from app.worker import WorkerSettings
        logger.info("  ✓ WorkerSettings imported")
        
    except Exception as e:
        _startup_error = f"Import error: {str(e)}"
        _startup_error_time = time.time()
        logger.error("=" * 60)
        logger.error("❌ FATAL: Failed to import worker dependencies")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        logger.error("=" * 60)
        logger.error("💡 Common causes:")
        logger.error("   - Missing environment variables (check secrets)")
        logger.error("   - Redis connection string invalid (REDIS_URL)")
        logger.error("   - Missing Python dependencies")
        logger.error("=" * 60)
        
        # Keep health server running for 60 seconds to allow log viewing
        logger.info("⏳ Keeping container alive for 60s to allow log viewing...")
        time.sleep(60)
        sys.exit(1)
    
    # ================================================================
    # STEP 3: Start Arq worker (may fail during Redis connection)
    # ================================================================
    logger.info("🚀 Starting Arq worker...")
    
    try:
        # Mark as ready AFTER imports succeed but BEFORE run_worker
        # run_worker will block, so we mark ready here
        # The actual Redis connection happens inside run_worker's startup hook
        _worker_ready.set()
        logger.info("✅ Worker marked as ready - entering main loop")
        
        # run_worker is SYNCHRONOUS and manages its own event loop
        # Do NOT wrap in asyncio.run() as arq handles its own loop
        run_worker(WorkerSettings)
        
    except KeyboardInterrupt:
        logger.info("🛑 Worker interrupted by user")
    except Exception as e:
        _worker_ready.clear()
        _startup_error = f"Worker error: {str(e)}"
        _startup_error_time = time.time()
        
        logger.error("=" * 60)
        logger.error("❌ FATAL: Arq worker failed to start")
        logger.error("=" * 60)
        logger.error(f"Error: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        logger.error("=" * 60)
        logger.error("💡 Common causes:")
        logger.error("   - Redis not reachable (check VPC connector)")
        logger.error("   - Redis URL format incorrect")
        logger.error("   - Redis authentication failed")
        logger.error("=" * 60)
        
        # Keep health server running for 60 seconds to allow log viewing
        logger.info("⏳ Keeping container alive for 60s to allow log viewing...")
        time.sleep(60)
        sys.exit(1)
    finally:
        health_server.shutdown()
        logger.info("👋 Worker shutdown complete")


if __name__ == "__main__":
    main()
