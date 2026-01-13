"""
Jobs Management Routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from arq.jobs import Job, JobStatus
import redis.asyncio as redis
import logging

from ..core.deps import get_current_user, get_redis_client
from ..core.user_profile import UserProfile

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    current_user: UserProfile = Depends(get_current_user)
):
    """
    Cancel an ongoing background job.
    This triggers an abort() on the arq job, raising asyncio.CancelledError in the worker.
    """
    pool = request.app.state.arq_pool
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job queue not available"
        )

    try:
        # 1. Always set cancellation flag in Redis (for non-Arq jobs or polling checks)
        client = get_redis_client()
        await client.set(f"cancel:{job_id}", "1", ex=3600)
        await client.close()
        
        # 2. Try to abort Arq job (if it exists)
        try:
            job = Job(job_id, redis=pool)
            job_status = await job.status()
            
            if job_status != JobStatus.not_found:
                await job.abort()
                logger.info(f"✅ Arq Job {job_id} aborted")
                return {"success": True, "message": "Job cancellation requested"}
        except Exception as e:
            logger.warning(f"⚠️ Arq abort failed (might be non-arq job): {e}")

        # If we got here, we at least set the flag
        return {"success": True, "message": "Cancellation flag set"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
