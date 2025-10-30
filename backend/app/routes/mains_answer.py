"""
UPSC Mains Answer Generation endpoint
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import logging
import time
from openai import OpenAI, RateLimitError

from ..core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class MainsAnswerRequest(BaseModel):
    question: str
    word_count: int = 500
    include_diagrams: bool = True

class MainsAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]
    diagram_suggestions: Optional[List[str]] = None
    word_count_actual: int

def generate_mains_answer_with_gpt(question: str, context: str, word_count: int, include_diagrams: bool, api_key: str, max_retries: int = 3) -> Dict[str, Any]:
    """Generate UPSC Mains style answer using GPT with retry logic"""
    wait_time = 1.0
    
    for attempt in range(max_retries):
        try:
            client = OpenAI(api_key=api_key)
            
            # Create system prompt for UPSC Mains style
            system_prompt = f"""You are an expert UPSC Geography teacher and evaluator. Generate a comprehensive answer in UPSC Mains style with the following characteristics:

1. **Structure**: Introduction → Main Body (with sub-points) → Conclusion
2. **Length**: Approximately {word_count} words
3. **Style**: Academic, analytical, and well-structured
4. **Content**: Use the provided context as primary source, supplement with your knowledge
5. **Format**: Use proper headings, bullet points, and logical flow
6. **UPSC Standards**: Include relevant examples, case studies, and current affairs where applicable

Answer format:
- Start with a brief introduction (2-3 sentences)
- Use clear headings for main points
- Include sub-points with specific examples
- End with a concise conclusion
- Use Indian examples and case studies when relevant"""

            user_prompt = f"""Question: {question}

Reference Context from Study Materials:
{context}

Generate a comprehensive UPSC Mains answer following the structure and style guidelines above."""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            completion = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=2000  # Allow for longer responses
            )
            
            answer = completion.choices[0].message.content
            
            # Generate diagram suggestions if requested
            diagram_suggestions = []
            if include_diagrams:
                try:
                    diagram_prompt = f"""Based on this UPSC Mains answer about Geography, suggest 2-3 relevant diagrams that would enhance the answer:

Answer: {answer[:1000]}...

Provide specific diagram suggestions that would be useful for this topic."""

                    diagram_completion = client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=[{"role": "user", "content": diagram_prompt}],
                        temperature=0.2,
                        max_tokens=300
                    )
                    
                    diagram_text = diagram_completion.choices[0].message.content
                    # Parse diagram suggestions (assuming they're in a list format)
                    diagram_suggestions = [line.strip("- ").strip() for line in diagram_text.split("\n") if line.strip() and not line.strip().startswith("Based on")]
                    
                except Exception as e:
                    logger.warning(f"⚠️ Failed to generate diagram suggestions: {e}")
                    diagram_suggestions = ["Flow chart showing the main concepts", "Map showing relevant geographical features"]
            
            return {
                "answer": answer,
                "diagram_suggestions": diagram_suggestions
            }

        except RateLimitError as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Rate limit hit, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                wait_time *= 2
            else:
                logger.warning("⚠️ Rate limit persists, using basic answer format")
                return {
                    "answer": f"**UPSC Mains Answer**\n\n{context}\n\n*Note: This is a basic response due to API limitations. For a full UPSC-style answer, please try again later.*",
                    "diagram_suggestions": ["Flow chart of main concepts", "Relevant geographical map"]
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to generate mains answer: {e}")
            return {
                "answer": f"**UPSC Mains Answer**\n\n{context}\n\n*Note: This is a basic response due to technical limitations.*",
                "diagram_suggestions": ["Flow chart of main concepts", "Relevant geographical map"]
            }

@router.post("/generate")
async def generate_mains_answer(request: Request, mains_request: MainsAnswerRequest):
    """
    Generate a comprehensive UPSC Mains style answer for Geography questions.
    """
    try:
        # Switch to the enriched collection
        chroma_handler = request.app.state.chroma_handler
        chroma_handler.switch_to_collection("geography_docs_enriched")
        
        # Get relevant chunks using enhanced retrieval
        chunks = chroma_handler.query_documents(
            mains_request.question, 
            k=10  # Get more chunks for comprehensive answer
        )
        
        if not chunks:
            return MainsAnswerResponse(
                question=mains_request.question,
                answer="No relevant information found in the uploaded documents for this question.",
                sources=[],
                diagram_suggestions=[],
                word_count_actual=0
            )

        # Prepare context and sources
        context = "\n\n".join(chunk["content"] for chunk in chunks)
        sources = []
        seen = set()
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            filename = metadata.get("filename", "Unknown")
            chapter = metadata.get("chapter", "Unknown")
            section = metadata.get("section", "Unknown")
            
            # Create unique key based on available metadata
            key = (filename, chapter, section)
            
            if key not in seen:
                source_info = {
                    "filename": filename,
                    "chapter": chapter,
                    "section": section
                }
                sources.append(source_info)
                seen.add(key)

        # Generate answer using GPT if available
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            result = generate_mains_answer_with_gpt(
                mains_request.question, 
                context, 
                mains_request.word_count,
                mains_request.include_diagrams,
                api_key
            )
            answer = result["answer"]
            diagram_suggestions = result["diagram_suggestions"]
        else:
            answer = f"**UPSC Mains Answer**\n\n{context}\n\n*Note: OpenAI API key not available. This is a basic response.*"
            diagram_suggestions = ["Flow chart of main concepts", "Relevant geographical map"]

        # Calculate actual word count
        word_count_actual = len(answer.split())

        return MainsAnswerResponse(
            question=mains_request.question,
            answer=answer,
            sources=sources,
            diagram_suggestions=diagram_suggestions,
            word_count_actual=word_count_actual
        )

    except Exception as e:
        logger.error(f"❌ Mains answer generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
