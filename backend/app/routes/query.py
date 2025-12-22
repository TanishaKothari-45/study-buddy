"""
Query endpoint for the Geography Q&A bot - FIXED VERSION
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging
import time
import uuid
import json
import google.generativeai as genai  # ✅ ADDED

from ..core.config import settings
from ..utils.similarity_checker import SimilarityChecker
from ..core.deps import get_current_user
from ..models.user import User
from ..utils.user_api_key import get_gemini_api_key_for_request
from ..gemini_core import settings_gemini_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Global default (fallback)
GEMINI_API_KEY_SYSTEM = settings_gemini_key.GEMINI_API_KEY

class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    k: int = 10

class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]

def remove_overlap_text(chunks: List[str], min_overlap_words: int = 20, similarity_threshold: float = 0.6) -> str:
    """Combine chunks while removing overlapping text portions using fuzzy matching."""
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
        overlap_size = min(100, len(combined.split()) // 2, len(next_chunk.split()))
        
        if overlap_size < min_overlap_words:
            combined += " " + next_chunk
            continue
        
        tail = " ".join(combined.split()[-overlap_size:])
        head = " ".join(next_chunk.split()[:overlap_size])
        ratio = SequenceMatcher(None, tail.lower(), head.lower()).ratio()
        
        if ratio > similarity_threshold:
            overlap_end = int(len(head.split()) * ratio)
            if overlap_end > 0:
                next_chunk_cleaned = " ".join(next_chunk.split()[overlap_end:])
                combined += " " + next_chunk_cleaned
                overlap_removed_count += 1
                total_overlap_words += overlap_end
            else:
                combined += " " + next_chunk
        else:
            combined += " " + next_chunk
    
    return re.sub(r'\s+', ' ', combined).strip()

def deduplicate_chunks(docs: List[Any], min_overlap_words: int = 20, similarity_threshold: float = 0.6) -> str:
    """Deduplicate overlapping text from retrieved chunks."""
    chunks = [doc.page_content for doc in docs if doc.page_content and doc.page_content.strip()]
    if not chunks:
        return ""
    return remove_overlap_text(chunks, min_overlap_words, similarity_threshold)

# System instruction
SYSTEM_INSTRUCTION = (
    "You are a friendly and knowledgeable UPSC Study Buddy who explains "
    "geography concepts in a simple, engaging way. When explaining: "
    "- Use the context from study materials first. "
    "- Then add your own understanding only when it helps make things clearer. "
    "- Break complex ideas into small, easy-to-understand steps. "
    "- Use examples, analogies, and relatable comparisons. "
    "- Avoid jargon unless necessary, and when you use it, explain it simply. "
    "- Your tone should be warm, clear, and human — like a good teacher. "
    "- When relevant, link the concept to real-world or Indian examples. "
    "- Don't just repeat text — *explain it like you're teaching someone new to the topic*. "
    "- If you don't have specific information about something, say so clearly."
)

MAX_SESSION_AGE = 3600
MAX_MESSAGES_IN_HISTORY = 10

@router.post("/stream")
async def query_pdfs_stream(
    request: Request, 
    query_request: QueryRequest,
    current_user: User = Depends(get_current_user)  # ✅ MOVED HERE (correct placement)
):
    """
    Streaming version with Gemini Flash using user's API key.
    Returns Server-Sent Events (SSE) stream.
    """
    async def generate_stream():
        try:
            # Initialize session storage
            if not hasattr(request.app.state, 'chat_sessions'):
                logger.info("🔧 Initializing chat session storage...")
                request.app.state.chat_sessions = {}
                request.app.state.similarity_checker = SimilarityChecker()
                logger.info("✅ Session storage initialized")
            
            # Clean up old sessions
            current_time = time.time()
            sessions_to_delete = [
                sid for sid, sess in request.app.state.chat_sessions.items()
                if current_time - sess.get("created_at", 0) > MAX_SESSION_AGE
            ]
            for sid in sessions_to_delete:
                del request.app.state.chat_sessions[sid]
            
            # Get or create session
            session_id = query_request.session_id or str(uuid.uuid4())
            session = request.app.state.chat_sessions.get(session_id)
            is_new_session = session is None
            
            # ✅ FIXED: Proper error handling for API key retrieval
            if is_new_session:
                gemini_api_key = None
                try:
                    # Try to get user's API key
                    gemini_api_key = get_gemini_api_key_for_request(current_user)
                    logger.info(f"✅ Using user's Gemini API key for user {current_user.id}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get user API key: {e}, falling back to system key")
                    gemini_api_key = GEMINI_API_KEY_SYSTEM
                
                # Final validation
                if not gemini_api_key:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'No Gemini API key available. Please add your API key in settings.'})}\n\n"
                    return
                
                # ✅ FIXED: Configure Gemini properly
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel(
                    'gemini-2.0-flash-exp',  # ✅ FIXED: Correct model name
                    system_instruction=SYSTEM_INSTRUCTION
                )
                chat = model.start_chat(history=[])
                
                # ✅ FIXED: Session object structure (removed openai_client)
                session = {
                    "model": model,
                    "chat": chat,
                    "gemini_api_key": gemini_api_key,
                    "messages": [],  # For tracking (not used by Gemini directly)
                    "last_question": None,
                    "last_embedding": None,
                    "cached_docs": None,
                    "cached_context": None,
                    "created_at": current_time,
                    "user_id": str(current_user.id) if current_user else "anonymous"
                }
                request.app.state.chat_sessions[session_id] = session
                logger.info(f"🆕 Created new Gemini chat session: {session_id}")
            
            # Similarity check and embedding
            current_embedding = request.app.state.similarity_checker.encode(query_request.question)
            
            # Determine if retrieval is needed
            should_retrieve = True
            include_previous_context = False
            
            if not is_new_session and session["last_question"] and session["last_embedding"] is not None:
                import numpy as np
                similarity = float(
                    np.dot(current_embedding, session["last_embedding"]) / 
                    (np.linalg.norm(current_embedding) * np.linalg.norm(session["last_embedding"]))
                )
                
                if similarity >= 0.75:
                    should_retrieve = False
                    logger.info(f"✅ High similarity ({similarity:.2f}) - using cached context")
                elif similarity >= 0.50:
                    include_previous_context = True
                    logger.info(f"⚠️ Medium similarity ({similarity:.2f}) - fresh + previous context")
            
            # Retrieve documents if needed
            if should_retrieve:
                pinecone_handler = request.app.state.vector_handler
                retriever = pinecone_handler.get_retriever_for_mode(
                    mode="concept",
                    use_content_store=True,
                    k=query_request.k
                )
                
                docs = retriever.invoke(query_request.question) if hasattr(retriever, 'invoke') else retriever.get_relevant_documents(query_request.question)
                
                if docs:
                    context = deduplicate_chunks(docs, min_overlap_words=20, similarity_threshold=0.6)
                    if include_previous_context and session["cached_context"]:
                        context = session["cached_context"] + "\n\n" + context
                    session["cached_docs"] = docs
                    session["cached_context"] = context
                else:
                    context = ""
            else:
                docs = session["cached_docs"]
                context = session["cached_context"]
            
            # Prepare sources
            sources = []
            if docs:
                seen = set()
                for doc in docs:
                    metadata = doc.metadata
                    filename = metadata.get("filename", "Unknown")
                    page_number = metadata.get("page_number")
                    key = (filename, page_number) if page_number else (filename,)
                    
                    if key not in seen:
                        source_info = {
                            "filename": filename,
                            "chapter": metadata.get("chapter", "Unknown"),
                            "section": metadata.get("section", "Unknown"),
                        }
                        if page_number:
                            source_info["page_number"] = page_number
                        sources.append(source_info)
                        seen.add(key)
            
            # Send sources first
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
            
            # Format message
            user_message = (
                f"Reference Context from Study Materials:\n{context}\n\n"
                f"Question: {query_request.question}\n\n"
                "Please explain this concept clearly and simply, step by step."
            )
            
            # Track message (for history management)
            session["messages"].append({"role": "user", "content": user_message})
            if len(session["messages"]) > MAX_MESSAGES_IN_HISTORY:
                session["messages"] = session["messages"][-MAX_MESSAGES_IN_HISTORY:]
            
            # ✅ FIXED: Stream response from Gemini (not OpenAI)
            response = session["chat"].send_message(user_message, stream=True)
            
            full_response = ""
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'type': 'content', 'content': chunk.text})}\n\n"
            
            # Add assistant response to history
            session["messages"].append({"role": "assistant", "content": full_response})
            session["last_question"] = query_request.question
            session["last_embedding"] = current_embedding
            
            # Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            logger.error(f"❌ Streaming error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.post("/")
async def query_pdfs(
    request: Request, 
    query_request: QueryRequest,
    current_user: User = Depends(get_current_user)  # ✅ MOVED HERE
):
    """
    Non-streaming endpoint (for compatibility).
    Use /stream for better UX.
    """
    logger.info(f"🚀 [QUERY] Received query request: '{query_request.question[:100]}...' (k={query_request.k})")
    
    try:
        # Initialize session storage
        if not hasattr(request.app.state, 'chat_sessions'):
            logger.info("🔧 Initializing chat session storage...")
            request.app.state.chat_sessions = {}
            request.app.state.similarity_checker = SimilarityChecker()
            logger.info("✅ Session storage initialized")
        
        # Clean up old sessions
        current_time = time.time()
        sessions_to_delete = [
            sid for sid, sess in request.app.state.chat_sessions.items()
            if current_time - sess.get("created_at", 0) > MAX_SESSION_AGE
        ]
        for sid in sessions_to_delete:
            del request.app.state.chat_sessions[sid]
        
        # Generate session ID
        session_id = query_request.session_id or str(uuid.uuid4())
        logger.info(f"📋 Session ID: {session_id}")
        
        # Get or create session
        session = request.app.state.chat_sessions.get(session_id)
        is_new_session = session is None
        
        if is_new_session:
            logger.info(f"🆕 Creating new chat session: {session_id}")
            
            # Get Gemini API key
            gemini_api_key = None
            try:
                gemini_api_key = get_gemini_api_key_for_request(current_user)
                logger.info(f"✅ Using user's Gemini API key")
            except Exception as e:
                logger.warning(f"⚠️ Falling back to system key: {e}")
                gemini_api_key = GEMINI_API_KEY_SYSTEM
            
            if not gemini_api_key:
                raise HTTPException(400, "No Gemini API key available. Please add your API key in settings.")
            
            # Configure Gemini
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel(
                'gemini-2.0-flash-exp',
                system_instruction=SYSTEM_INSTRUCTION
            )
            chat = model.start_chat(history=[])
            
            session = {
                "model": model,
                "chat": chat,
                "gemini_api_key": gemini_api_key,
                "messages": [],
                "last_question": None,
                "last_embedding": None,
                "cached_docs": None,
                "cached_context": None,
                "created_at": current_time,
                "user_id": str(current_user.id) if current_user else "anonymous"
            }
            request.app.state.chat_sessions[session_id] = session
        
        # [REST OF THE LOGIC SAME AS STREAMING - similarity check, retrieval, etc.]
        # ... (keeping it short, but follow same pattern as streaming)
        
        # Get Pinecone handler
        pinecone_handler = request.app.state.vector_handler
        
        # Encode current question
        current_embedding = request.app.state.similarity_checker.encode(query_request.question)
        
        # Similarity check (same logic as streaming)
        should_retrieve = True
        include_previous_context = False
        
        if not is_new_session and session["last_question"] and session["last_embedding"] is not None:
            import numpy as np
            similarity = float(
                np.dot(current_embedding, session["last_embedding"]) / 
                (np.linalg.norm(current_embedding) * np.linalg.norm(session["last_embedding"]))
            )
            
            if similarity >= 0.75:
                should_retrieve = False
            elif similarity >= 0.50:
                include_previous_context = True
        
        # Retrieve documents if needed
        if should_retrieve:
            retriever = pinecone_handler.get_retriever_for_mode(
                mode="concept",
                use_content_store=True,
                k=query_request.k
            )
            
            docs = retriever.invoke(query_request.question) if hasattr(retriever, 'invoke') else retriever.get_relevant_documents(query_request.question)
            
            if not docs:
                return QueryResponse(
                    question=query_request.question,
                    answer="No relevant information found in the uploaded documents.",
                    sources=[]
                )
            
            context = deduplicate_chunks(docs, min_overlap_words=20, similarity_threshold=0.6)
            
            if include_previous_context and session["cached_context"]:
                context = session["cached_context"] + "\n\n" + context
            
            session["cached_docs"] = docs
            session["cached_context"] = context
        else:
            docs = session["cached_docs"]
            context = session["cached_context"]
        
        # Prepare sources
        sources = []
        seen = set()
        for doc in docs:
            metadata = doc.metadata
            filename = metadata.get("filename", "Unknown")
            page_number = metadata.get("page_number")
            key = (filename, page_number) if page_number else (filename,)
            
            if key not in seen:
                source_info = {
                    "filename": filename,
                    "chapter": metadata.get("chapter", "Unknown"),
                    "section": metadata.get("section", "Unknown"),
                }
                if page_number:
                    source_info["page_number"] = page_number
                sources.append(source_info)
                seen.add(key)
        
        # Generate answer using Gemini
        logger.info(f"🤖 [QUERY] Step 6: Generating answer using Gemini Flash...")
        try:
            user_message = (
                f"Reference Context from Study Materials:\n{context}\n\n"
                f"Question: {query_request.question}\n\n"
                "Please explain this concept clearly and simply, step by step."
            )
            
            session["messages"].append({"role": "user", "content": user_message})
            if len(session["messages"]) > MAX_MESSAGES_IN_HISTORY:
                session["messages"] = session["messages"][-MAX_MESSAGES_IN_HISTORY:]
            
            # Send to Gemini (non-streaming)
            response = session["chat"].send_message(user_message)
            answer = response.text
            
            logger.info(f"   → Generated answer length: {len(answer)} chars")
            
            # Add assistant response to history
            session["messages"].append({"role": "assistant", "content": answer})
            session["last_question"] = query_request.question
            session["last_embedding"] = current_embedding
            
        except Exception as e:
            logger.error(f"❌ Failed to generate answer with Gemini: {e}")
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