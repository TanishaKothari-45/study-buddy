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

def remove_overlap_text(chunks: List[str], min_overlap_words: int = 20, similarity_threshold: float = 0.6) -> str:
    """
    Combine chunks while removing overlapping text portions using fuzzy matching.
    
    This is a safer, less aggressive approach that:
    - Uses fuzzy matching (SequenceMatcher) to handle slight variations
    - Requires minimum overlap (20 words) and similarity threshold (60%)
    - Works on any chunks, not just split ones
    - Preserves content while removing redundant overlap
    
    Args:
        chunks: List of text chunks to combine
        min_overlap_words: Minimum number of words to consider for overlap (default: 20)
        similarity_threshold: Minimum similarity ratio to consider overlap (default: 0.6)
        
    Returns:
        Combined text with overlapping portions removed
    """
    import re
    from difflib import SequenceMatcher
    
    if not chunks:
        return ""
    
    if len(chunks) == 1:
        return chunks[0]
    
    combined = chunks[0]
    overlap_removed_count = 0
    total_overlap_words = 0
    
    for i, next_chunk in enumerate(chunks[1:], 1):
        # Find overlap between tail of combined and head of next_chunk
        # Check up to 100 words or half of combined text (whichever is smaller)
        overlap_size = min(100, len(combined.split()) // 2, len(next_chunk.split()))
        
        if overlap_size < min_overlap_words:
            # Not enough text to check for overlap, just append
            combined += " " + next_chunk
            continue
        
        tail = " ".join(combined.split()[-overlap_size:])
        head = " ".join(next_chunk.split()[:overlap_size])
        
        # Fuzzy match overlap (case-insensitive)
        ratio = SequenceMatcher(None, tail.lower(), head.lower()).ratio()
        
        if ratio > similarity_threshold:
            # Found overlap - remove overlapping part from next_chunk
            overlap_end = int(len(head.split()) * ratio)
            if overlap_end > 0:
                next_chunk_cleaned = " ".join(next_chunk.split()[overlap_end:])
                combined += " " + next_chunk_cleaned
                overlap_removed_count += 1
                total_overlap_words += overlap_end
                logger.debug(f"      → Removed ~{overlap_end} overlapping words between chunk {i} and {i+1} (similarity: {ratio:.2f})")
            else:
                # Overlap too small, keep as-is
                combined += " " + next_chunk
        else:
            # No significant overlap found, keep as-is
            combined += " " + next_chunk
    
    if overlap_removed_count > 0:
        logger.debug(f"   → Removed overlap from {overlap_removed_count} chunk pairs (~{total_overlap_words} words total)")
    
    # Final cleanup of whitespace
    return re.sub(r'\s+', ' ', combined).strip()


def deduplicate_chunks(docs: List[Any], min_overlap_words: int = 20, similarity_threshold: float = 0.6) -> str:
    """
    Deduplicate overlapping text from retrieved chunks before sending to LLM.
    
    This function extracts page_content from documents, removes overlaps using
    fuzzy matching, and returns a single combined text string.
    
    Args:
        docs: List of Document objects from retriever
        min_overlap_words: Minimum words to consider for overlap (default: 20)
        similarity_threshold: Minimum similarity ratio for overlap (default: 0.6)
        
    Returns:
        Combined text with overlapping portions removed
    """
    # Extract text content from documents
    chunks = [doc.page_content for doc in docs if doc.page_content and doc.page_content.strip()]
    
    if not chunks:
        return ""
    
    # Remove overlaps and combine
    merged_text = remove_overlap_text(chunks, min_overlap_words, similarity_threshold)
    
    return merged_text


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
    Query using LangChain retriever with content store enrichment.
    
    Flow:
    1. Create LangChain retriever with similarity search (k=6)
    2. Retriever gets documents from Pinecone (with chunk_ids)
    3. ContentStoreRetriever wrapper enriches with full content from SQLite
    4. Pass enriched documents to LLM for answer generation
    """
    logger.info(f"🚀 [QUERY] Received query request: '{query_request.question[:100]}...' (k={query_request.k})")
    
    try:
        # Get Pinecone handler
        logger.info(f"📦 [QUERY] Step 1: Getting Pinecone handler from app state...")
        pinecone_handler = request.app.state.vector_handler
        logger.info(f"✅ [QUERY] Pinecone handler retrieved: {type(pinecone_handler).__name__}")
        
        # Create LangChain retriever configured for "concept" mode (explaining concepts)
        # Allows k to be customized via request parameter
        logger.info(f"🔧 [QUERY] Step 2: Creating retriever for 'concept' mode (k={query_request.k}, use_content_store=True)...")
        retriever = pinecone_handler.get_retriever_for_mode(
            mode="concept",
            use_content_store=True,
            k=query_request.k  # Use k from request (default: 5, but can be overridden)
        )
        logger.info(f"✅ [QUERY] Retriever created: {type(retriever).__name__}")
        
        logger.info(f"🔍 [QUERY] Step 3: Retrieving documents for query: '{query_request.question[:100]}...'")
        
        # Get relevant documents (already enriched with full content from SQLite)
        # Use invoke() for newer LangChain versions, fallback to get_relevant_documents() for compatibility
        try:
            # Try using invoke() (LangChain 0.1.46+)
            if hasattr(retriever, 'invoke'):
                logger.debug(f"   → Using invoke() method")
                docs = retriever.invoke(query_request.question)
            else:
                # Fallback to deprecated method for older versions
                logger.debug(f"   → Using get_relevant_documents() method")
                docs = retriever.get_relevant_documents(query_request.question)
        except Exception as e:
            # If invoke fails, try deprecated method
            logger.warning(f"⚠️ [QUERY] invoke() failed, trying get_relevant_documents(): {e}")
            docs = retriever.get_relevant_documents(query_request.question)
        
        if not docs:
            logger.warning(f"⚠️ [QUERY] No documents retrieved")
            return QueryResponse(
                question=query_request.question,
                answer="No relevant information found in the uploaded documents.",
                sources=[]
            )
        
        logger.info(f"✅ [QUERY] Retrieved {len(docs)} documents from retriever")
        
        # Prepare context from documents (page_content has full content from SQLite)
        logger.info(f"📝 [QUERY] Step 4: Preparing context from {len(docs)} documents...")
        
        # Calculate original context length for comparison
        original_context_length = sum(len(doc.page_content) for doc in docs)
        
        # Deduplicate overlapping text using safer fuzzy matching approach
        logger.info(f"   → Removing overlapping text using fuzzy matching (min_overlap=20 words, similarity>60%)...")
        context = deduplicate_chunks(docs, min_overlap_words=20, similarity_threshold=0.6)
        
        # Calculate overlap removed
        overlap_removed = original_context_length - len(context)
        if overlap_removed > 0:
            # Estimate token savings (rough: 1 token ≈ 4 characters)
            estimated_tokens_saved = overlap_removed // 4
            logger.info(f"   ✅ Overlap removal complete:")
            logger.info(f"      • Overlap removed: {overlap_removed} characters (~{estimated_tokens_saved} tokens)")
            logger.info(f"      • Original: {len(docs)} docs, {original_context_length} chars")
            logger.info(f"      • After dedup: {len(context)} chars")
        else:
            logger.info(f"   → No significant overlap detected")
        
        logger.info(f"   → Final context length: {len(context)} characters")
        
        # Prepare sources from document metadata (use original docs for source tracking)
        logger.info(f"📋 [QUERY] Step 5: Extracting source metadata...")
        sources = []
        seen = set()
        sqlite_count = 0
        preview_count = 0
        
        for doc in docs:
            metadata = doc.metadata
            filename = metadata.get("filename", "Unknown")
            page_number = metadata.get("page_number")
            chapter = metadata.get("chapter", "Unknown")
            section = metadata.get("section", "Unknown")
            content_source = metadata.get("_content_source", "unknown")
            
            # Track content sources
            if content_source == "content_store":
                sqlite_count += 1
            elif content_source == "content_preview":
                preview_count += 1
            
            # Create unique key based on available metadata
            if page_number:
                key = (filename, page_number)
            else:
                key = (filename, chapter, section)
            
            if key not in seen:
                source_info = {
                    "filename": filename,
                    "chapter": chapter,
                    "section": section,
                    "content_source": content_source  # "content_store" or "content_preview"
                }
                if page_number:
                    source_info["page_number"] = page_number
                sources.append(source_info)
                seen.add(key)
        
        logger.info(f"📚 [QUERY] Context preparation complete:")
        logger.info(f"   • Documents retrieved: {len(docs)}")
        logger.info(f"   • Context length: {len(context)} chars")
        logger.info(f"   • Unique sources: {len(sources)}")
        logger.info(f"   • Content sources: {sqlite_count} from SQLite, {preview_count} from Pinecone preview")

        # Format answer using GPT if available
        logger.info(f"🤖 [QUERY] Step 6: Generating answer using GPT...")
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            logger.info(f"   → Using OpenAI API (model: {settings.LLM_MODEL})")
            answer = format_answer_with_gpt(context, query_request.question, api_key)
            logger.info(f"   → Generated answer length: {len(answer)} chars")
        else:
            logger.warning(f"   ⚠️ No OpenAI API key - returning raw context")
            answer = f"Based on the available information:\n\n{context}"

        logger.info(f"✅ [QUERY] Query processing complete - returning response")
        return QueryResponse(
            question=query_request.question,
            answer=answer,
            sources=sources
        )

    except Exception as e:
        logger.error(f"❌ Query processing failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))