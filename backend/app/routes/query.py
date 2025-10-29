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

def format_answer_with_gpt(context: str, question: str, api_key: str, max_retries: int = 3) -> str:
    """Format answer using GPT with retry logic"""
    wait_time = 1.0
    
    for attempt in range(max_retries):
        try:
            client = OpenAI(api_key=api_key)
            completion = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a friendly and knowledgeable UPSC Study Buddy who explains "
                            "geography concepts in a simple, engaging way. When explaining: "
                            "- Use the context from study materials first. "
                            "- Then add your own understanding only when it helps make things clearer. "
                            "- Break complex ideas into small, easy-to-understand steps. "
                            "- Use examples, analogies, and relatable comparisons. "
                            "- Avoid jargon unless necessary, and when you use it, explain it simply. "
                            "- Your tone should be warm, clear, and human — like a good teacher. "
                            "- When relevant, link the concept to real-world or Indian examples. "
                            "- Don’t just repeat text — *explain it like you’re teaching someone new to the topic*."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {question}\n\n"
                            f"Reference Context from Study Materials:\n{context}\n\n"
                            "Please explain this concept clearly and simply, step by step. "
                            "Use examples, analogies, and real-world connections where possible. "
                            "If something isn’t directly in the material, add it from your knowledge "
                            "(but only to clarify)."
                        )
                    }
                ],
                temperature=0.1,
                max_tokens=1000  # Increased to allow for more detailed answers
            )
            return completion.choices[0].message.content

        except RateLimitError as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                wait_time *= 2
            else:
                logger.warning("⚠️ Rate limit persists, using raw context")
                return f"Based on the available information:\n\n{context}"
                
        except Exception as e:
            logger.error(f"❌ Failed to format answer: {e}")
            return f"Based on the available information:\n\n{context}"

@router.post("/")
async def query_pdfs(request: Request, query_request: QueryRequest):
    """
    Query the enriched ChromaDB collection for answers.
    """
    try:
        # Switch to the new collection for enriched chunks
        chroma_handler = request.app.state.chroma_handler
        chroma_handler.switch_to_collection("geography_docs_enriched")
        
        # Get relevant chunks using Sentence Transformers (local)
        chunks = chroma_handler.query_documents(
            query_request.question, 
            query_request.k
        )
        
        if not chunks:
            return QueryResponse(
                question=query_request.question,
                answer="No relevant information found in the uploaded documents.",
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

        # Format answer using GPT if available
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            answer = format_answer_with_gpt(context, query_request.question, api_key)
        else:
            answer = f"Based on the available information:\n\n{context}"

        return QueryResponse(
            question=query_request.question,
            answer=answer,
            sources=sources
        )

    except Exception as e:
        logger.error(f"❌ Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))