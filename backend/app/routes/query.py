"""
Query endpoint for the Geography Q&A bot
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import logging
import time
from openai import OpenAI, RateLimitError
from ..core.env import load_env_vars

# Ensure environment variables are loaded
load_env_vars()

from ..core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryRequest(BaseModel):
    question: str
    k: int = 5

class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]

@router.post("/", response_model=QueryResponse)
async def query_pdfs(request: Request, query_request: QueryRequest):
    """Query PDFs and generate answer"""
    try:
        # Get ChromaDB handler from app state
        chroma_handler = request.app.state.chroma_handler
        
        # Get relevant chunks
        chunks = chroma_handler.query_documents(
            query_request.question, 
            query_request.k
        )
        
        if not chunks:
            return QueryResponse(
                question=query_request.question,
                answer="No relevant information found.",
                sources=[]
            )

        # Prepare context and sources
        context = "\n\n".join(chunk["content"] for chunk in chunks)
        sources = []
        seen = set()
        for chunk in chunks:
            key = (chunk["metadata"]["filename"], chunk["metadata"]["page_number"])
            if key not in seen:
                sources.append({
                    "filename": chunk["metadata"]["filename"],
                    "page_number": chunk["metadata"]["page_number"]
                })
                seen.add(key)

        # Try to use OpenAI for answer generation
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            max_retries = 3
            wait_time = 1.0
            for attempt in range(max_retries):
                try:
                    client = OpenAI(api_key=api_key)
                    completion = client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=[
                            {"role": "system", "content": "You are a helpful AI assistant for UPSC Geography. Answer questions based on the provided context."},
                            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query_request.question}\n\nAnswer:"}
                        ],
                        temperature=0.1,
                        max_tokens=500
                    )
                    answer = completion.choices[0].message.content
                    logger.info("✅ Generated answer using OpenAI")
                    break
                except RateLimitError as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        wait_time *= 2  # Exponential backoff
                    else:
                        logger.warning(f"⚠️ Rate limit persists after {max_retries} retries, using fallback...")
                        answer = f"Here are the most relevant passages:\n\n{context}"
                except Exception as e:
                    logger.warning(f"⚠️ OpenAI answer generation failed: {e}")
                    answer = f"Here are the most relevant passages:\n\n{context}"
                    break
        else:
            # No OpenAI key, use raw context
            answer = f"Here are the most relevant passages:\n\n{context}"

        return QueryResponse(
            question=query_request.question,
            answer=answer,
            sources=sources
        )

    except Exception as e:
        logger.error(f"❌ Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))