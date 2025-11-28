"""
context_retriever.py

Shared context retrieval utility for fetching relevant documents from Pinecone/SQLite.
Used by both mains_answer.py and evaluate_answer.py for consistent retrieval logic.

Usage:
    from context_retriever import retrieve_context_for_question
    
    context, sources = retrieve_context_for_question(
        search_query="climate change impact agriculture",
        vector_handler=pinecone_handler,
        mode="mains"
    )
"""

import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

# Import the original deduplicate_chunks from query.py to use the same logic
try:
    from ..routes.query import deduplicate_chunks
except ImportError:
    # Fallback if import fails
    deduplicate_chunks = None
    logger.warning("Could not import deduplicate_chunks from query.py")


def extract_sources_from_docs(docs: List[Any]) -> List[Dict[str, Any]]:
    """
    Extract source metadata from retrieved documents.
    
    Args:
        docs: List of documents with metadata
    
    Returns:
        List of unique source dictionaries
    """
    sources = []
    seen = set()
    
    for doc in docs:
        metadata = getattr(doc, 'metadata', {})
        
        filename = metadata.get("filename", "Unknown")
        chapter = metadata.get("chapter", "Unknown")
        section = metadata.get("section", "Unknown")
        
        # Create unique key
        key = (filename, chapter, section)
        
        if key not in seen:
            source_info = {
                "filename": filename,
                "chapter": chapter,
                "section": section
            }
            sources.append(source_info)
            seen.add(key)
    
    return sources


def retrieve_context_for_question(
    search_query: str,
    vector_handler,
    mode: str = "mains",
    use_content_store: bool = True,
    k: int = 6
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Retrieve relevant context from vector store for a given search query.
    
    Args:
        search_query: Optimized search query (from question_parser)
        vector_handler: PineconeHandler or similar vector store handler
        mode: Retrieval mode ("mains", "concept", etc.)
        use_content_store: Whether to enrich with SQLite content store
        k: Number of documents to retrieve
    
    Returns:
        Tuple of (context_text, sources_list)
    """
    if not search_query or not search_query.strip():
        logger.warning("Empty search query provided")
        return "", []
    
    if not vector_handler:
        logger.error("No vector handler provided")
        return "", []
    
    try:
        logger.info(f"🔍 Retrieving context for query: {search_query[:80]}...")
        
        # Get retriever configured for the specified mode
        retriever = vector_handler.get_retriever_for_mode(
            mode=mode,
            use_content_store=use_content_store,
            k=k
        )
        
        # Retrieve documents
        try:
            if hasattr(retriever, 'invoke'):
                docs = retriever.invoke(search_query)
            else:
                docs = retriever.get_relevant_documents(search_query)
        except Exception as e:
            logger.warning(f"⚠️ invoke() failed, trying get_relevant_documents(): {e}")
            docs = retriever.get_relevant_documents(search_query)
        
        if not docs:
            logger.warning("⚠️ No documents retrieved")
            return "", []
        
        logger.info(f"✅ Retrieved {len(docs)} documents")
        
        # Deduplicate overlapping text using the same logic as query.py
        original_length = sum(len(doc.page_content) for doc in docs)
        
        if deduplicate_chunks:
            context = deduplicate_chunks(docs, min_overlap_words=20, similarity_threshold=0.6)
        else:
            # Simple fallback: just combine without deduplication
            context = "\n\n---\n\n".join([doc.page_content for doc in docs if doc.page_content])
        
        overlap_removed = original_length - len(context)
        if overlap_removed > 0:
            logger.info(f"   ✅ Removed {overlap_removed} chars of overlap")
        
        logger.info(f"   → Final context length: {len(context)} characters")
        
        # Extract sources
        sources = extract_sources_from_docs(docs)
        logger.info(f"   → Extracted {len(sources)} unique sources")
        
        return context, sources
        
    except Exception as e:
        logger.error(f"❌ Context retrieval failed: {e}", exc_info=True)
        return "", []


async def retrieve_context_async(
    search_query: str,
    vector_handler,
    mode: str = "mains",
    use_content_store: bool = True,
    k: int = 6
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Async wrapper for retrieve_context_for_question.
    Useful when called from async endpoints.
    """
    # The actual retrieval is synchronous, but we wrap it for consistency
    return retrieve_context_for_question(
        search_query=search_query,
        vector_handler=vector_handler,
        mode=mode,
        use_content_store=use_content_store,
        k=k
    )

