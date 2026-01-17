"""
Cron Job Endpoints (Vercel Cron / Cloud Scheduler)
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional

from ..core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Security: require CRON_SECRET header to prevent unauthorized triggers
async def verify_cron_secret(
    authorization: Optional[str] = Header(None)
):
    """
    Verify the Authorization header matches CRON_SECRET.
    Format: "Bearer <CRON_SECRET>"
    """
    # If no secret is set in env, we might want to block all access or allow (insecure)
    # Defaulting to secure-fail if not set
    expected_secret = os.getenv("CRON_SECRET")
    
    if not expected_secret:
        logger.warning("CRON_SECRET not set in environment - blocking cron request")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cron configuration error"
        )
        
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )

    # Check for "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != 'bearer':
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme"
        )
        
    if token != expected_secret:
        logger.warning(f"Invalid cron secret attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid logic"
        )
    
    return True


@router.get("/trigger-monthly-current-affairs")
async def trigger_monthly_current_affairs(
    authorized: bool = Depends(verify_cron_secret)
):
    """
    Monthly Current Affairs Download & Processing Job
    Triggered by Vercel Cron on the 2nd of every month at 2:00 AM UTC.
    
    Downloads VisionIAS monthly workbook, extracts Geography/Environment sections,
    and processes them into Pinecone + SQLite content store.
    """
    logger.info("⏰ [CRON] Monthly Current Affairs job triggered")
    
    try:
        from ..utils.current_affairs_downloader import (
            download_latest_visionias_workbook,
            process_extracted_pdf
        )
        from ..utils.pinecone_handler import PineconeHandler
        from ..utils.content_store import ContentStore
        
        # Initialize handlers
        pinecone_handler = PineconeHandler()
        content_store = ContentStore()
        
        # Step 1: Download and extract sections
        logger.info("📥 [CRON] Downloading VisionIAS workbook...")
        extracted_file = download_latest_visionias_workbook(extract_sections=True)
        
        if not extracted_file:
            raise Exception("Failed to download or extract workbook")
        
        logger.info(f"✅ [CRON] Downloaded: {extracted_file}")
        
        # Step 2: Process the extracted PDF
        logger.info("🔄 [CRON] Processing extracted PDF...")
        result = process_extracted_pdf(
            pdf_path=extracted_file,
            pinecone_handler=pinecone_handler,
            content_store=content_store
        )
        
        if result["status"] != "success":
            raise Exception(f"Processing failed: {result.get('reason', 'Unknown error')}")
        
        logger.info(f"✅ [CRON] Processing completed:")
        logger.info(f"    • Chunks added: {result['chunks_added']}")
        logger.info(f"    • Filename: {result['filename']}")
        
        # TODO: Send email notification (optional)
        # from ..utils.send_email import send_success_notification
        # send_success_notification(result['filename'], result['chunks_added'], 'vercel-cron')
        
        return {
            "status": "success",
            "message": "Current affairs processing completed",
            "details": {
                "filename": result["filename"],
                "chunks_added": result["chunks_added"],
                "pinecone_chunks": result.get("pinecone_chunks", 0),
                "sqlite_chunks": result.get("sqlite_chunks", 0)
            }
        }
        
    except Exception as e:
        logger.error(f"❌ [CRON] Monthly current affairs job failed: {e}", exc_info=True)
        
        # TODO: Send failure email notification (optional)
        # from ..utils.send_email import send_failure_notification
        # send_failure_notification('Monthly Current Affairs', 1, str(e))
        
        raise HTTPException(
            status_code=500,
            detail=f"Cron job failed: {str(e)}"
        )

