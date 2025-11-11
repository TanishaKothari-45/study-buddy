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
from ..routes.query import deduplicate_chunks

logger = logging.getLogger(__name__)
router = APIRouter()

class MainsAnswerRequest(BaseModel):
    question: str
    word_count: int = 500

class MainsAnswerResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]
    word_count_actual: int

def generate_mains_answer_with_gpt(question: str, context: str, word_count: int, api_key: str, max_retries: int = 1) -> Dict[str, Any]:
    """Generate UPSC Mains style answer using GPT with retry logic (only 1 retry to limit API calls)"""
    wait_time = 1.0
    
    for attempt in range(max_retries + 1):  # max_retries=1 means 2 total attempts (initial + 1 retry)
        try:
            client = OpenAI(api_key=api_key)
            
            # Create system prompt for UPSC Mains style
            system_prompt = f"""You are an expert UPSC Geography teacher, evaluator and answer-writing coach.

Generate a high-quality UPSC Mains style answer with the following properties:

STRUCTURE & FORMAT
1) Follow IBC format strictly → Introduction → Body (multi-dimensions) → Conclusion (1 para).

INTRODUCTION RULE:
The introduction MUST be 2–3 lines and should NOT be generic. It should do one or more of the following explicitly:
- define the concept clearly
- cite a current report / scheme / data point
- briefly describe the core problem or context
Example formats permitted:
• “According to NITI Aayog’s 2023 report, …”
• “X refers to … In India, this is significant because …”
• “Recently, [event/current affair] has highlighted …”
The intro must instantly set intellectual context — avoid vague opening lines.

2) Pay attention to directive words such as “Analyse”, “Discuss”, “Critically Examine”, “Evaluate” etc. Adjust structure, tone, argumentation based on directive.

→ DIRECTIVE WORD INTERPRETATION (MANDATORY):
Before writing the answer, interpret the directive and shape structure accordingly:
- Comment = take a stance & justify (if critically → both sides)
- Examine = probe deeper (causes / implications / way forward)
- Critically examine = strengths + weaknesses separately, then implications
- Discuss = broad overview → positives / negatives / causes / consequences
- Discuss critically = same as discuss but more rigorous reasoning
- Evaluate = assess worthiness → positives / negatives → give verdict
- Critically evaluate = same as evaluate but explicitly bring value judgement
- Analyse = break the topic into sub-parts and examine each dimension
- Explain = clarify how/why something is
- Elucidate = make clear using examples/data
- Elaborate = expand the core idea by adding dimensions / layers / reasoning in detail
- Substantiate = assert then support with evidence/reports/data
- Note = concise summary of what/when/how/why
- Justify = defend the given statement using evidence, data, logic.
- Assess = judge importance/impact; like evaluate but magnitude-focused.
- To what extent = assess degree (fully / partly / marginally) and give a balanced graded judgement.
- Illustrate = give examples / mini case illustrations to clarify.


3) Body must be arranged in sub-headings + bullet points. Use logical organisation (economic / social / political / environmental / geographic dimensions). Use inter-topic integration / inter-disciplinary linkage wherever relevant.

4) Maintain clarity, precision, short sentences, and zero fluff. Avoid jargon unless necessary.

CONTENT QUALITY
5) Use provided context as primary — supplement with advanced knowledge.
6) MUST Substantiate every major point with examples, case studies, gov data, NITI Aayog reports, NFHS statistics, IPCC, UN reports, or Geography-specific examples.
7) Use MAXIMUM real Indian examples, named locations, regions, rivers, climatic zones, coal belts, ports, industrial corridors, etc. eg: Brahmaputra valley, Gondwana coal, Mediterranean → Spain / SW Australia / Chile etc.
8) Must add human dimension even in physical geography answers (e.g. rainfall → cropping pattern, river regime → settlement, landforms → industrial location, Tribal displacement, Biodiversity loss, Pollutio ).
9) Every answer MUST include AT LEAST ONE inline diagram suggestion — this is compulsory. If the answer body is long, include 2–3. These may be flowcharts, maps, pie charts, timelines, or comparative tables.
10) Insert these diagram suggestions EXACTLY where they are relevant — inline — NOT at the end. Use short parenthetical suggestions, e.g. “(Suggested Diagram: India map showing monsoon onset dates)” or “(Suggested Diagram: Flowchart showing monsoon mechanism)”. They MUST appear embedded after introduction or inside the body section at appropriate points.

CONCLUSION RULE:
The conclusion must synthesise, not repeat. Prefer forward-looking outlook — policy suggestion, way forward, global best practice, SDG linkage.

LENGTH
~{word_count} words approx.

OUTPUT FORMAT
- crisp intro (2–3 lines)
- structured sub-headings
- bulletised content under each sub-heading
- examples + data throughout
- 1 para conclusion (forward looking / policy suggestion / synthesis)"""

            user_prompt = f"""Question: {question}

Reference Context from Study Materials:
{context}

Generate a comprehensive UPSC Mains answer following the UPSC structure instructions given in system prompt."""

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
            
            # Return the answer if successful
            if answer:
                return {
                    "answer": answer
                }
            else:
                raise ValueError("Empty response from OpenAI API")

        except RateLimitError as e:
            logger.warning(f"⚠️ Rate limit hit on attempt {attempt + 1}")
            if attempt < max_retries:
                logger.info(f"   Retrying once after {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                logger.warning("⚠️ Rate limit persists after retry, using fallback answer")
                return {
                    "answer": f"**UPSC Mains Answer**\n\n{context}\n\n*Note: This is a basic response due to API rate limits. Please try again later.*"
                }
                
        except Exception as e:
            logger.error(f"❌ Failed to generate mains answer on attempt {attempt + 1}: {e}")
            if attempt < max_retries:
                logger.info(f"   Retrying once after {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                logger.warning("⚠️ All attempts failed, using fallback answer")
                return {
                    "answer": f"**UPSC Mains Answer**\n\n{context}\n\n*Note: This is a basic response due to technical limitations.*"
                }
    
    # If loop completes without returning (shouldn't happen), return fallback
    logger.warning("⚠️ Unexpected: loop completed without return, using fallback answer")
    return {
        "answer": f"**UPSC Mains Answer**\n\n{context}\n\n*Note: This is a basic response due to technical limitations.*"
    }

@router.post("/generate")
async def generate_mains_answer(request: Request, mains_request: MainsAnswerRequest):
    """
    Generate a comprehensive UPSC Mains style answer for Geography questions.
    """
    try:
        logger.info(f"🚀 [MAINS] Received request: '{mains_request.question[:100]}...' (word_count={mains_request.word_count})")
        
        # Get Pinecone handler
        pinecone_handler = request.app.state.vector_handler
        
        # Get retriever configured for mains mode
        logger.info(f"🔧 [MAINS] Creating retriever for 'mains' mode...")
        retriever = pinecone_handler.get_retriever_for_mode("mains", use_content_store=True)
        
        # Retrieve documents
        logger.info(f"🔍 [MAINS] Retrieving documents...")
        try:
            if hasattr(retriever, 'invoke'):
                docs = retriever.invoke(mains_request.question)
            else:
                docs = retriever.get_relevant_documents(mains_request.question)
        except Exception as e:
            logger.warning(f"⚠️ [MAINS] invoke() failed, trying get_relevant_documents(): {e}")
            docs = retriever.get_relevant_documents(mains_request.question)
        
        if not docs:
            logger.warning(f"⚠️ [MAINS] No documents retrieved")
            return MainsAnswerResponse(
                question=mains_request.question,
                answer="No relevant information found in the uploaded documents for this question.",
                sources=[],
                word_count_actual=0
            )
        
        logger.info(f"✅ [MAINS] Retrieved {len(docs)} documents")
        
        # Deduplicate overlapping text before combining
        logger.info(f"📝 [MAINS] Removing overlapping text...")
        original_context_length = sum(len(doc.page_content) for doc in docs)
        context = deduplicate_chunks(docs, min_overlap_words=20, similarity_threshold=0.6)
        overlap_removed = original_context_length - len(context)
        
        if overlap_removed > 0:
            estimated_tokens_saved = overlap_removed // 4
            logger.info(f"   ✅ Removed {overlap_removed} chars (~{estimated_tokens_saved} tokens) of overlap")
        else:
            logger.info(f"   → No significant overlap detected")
        
        logger.info(f"   → Final context length: {len(context)} characters")
        
        # Prepare sources from document metadata
        logger.info(f"📋 [MAINS] Extracting source metadata...")
        sources = []
        seen = set()
        for doc in docs:
            metadata = doc.metadata
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
        logger.info(f"🤖 [MAINS] Generating answer using GPT...")
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            result = generate_mains_answer_with_gpt(
                mains_request.question, 
                context, 
                mains_request.word_count,
                api_key
            )
            answer = result["answer"]
            logger.info(f"✅ [MAINS] Answer generated: {len(answer)} characters")
        else:
            logger.warning(f"⚠️ [MAINS] No OpenAI API key - returning raw context")
            answer = f"**UPSC Mains Answer**\n\n{context}\n\n*Note: OpenAI API key not available. This is a basic response.*"

        # Calculate actual word count
        word_count_actual = len(answer.split())

        return MainsAnswerResponse(
            question=mains_request.question,
            answer=answer,
            sources=sources,
            word_count_actual=word_count_actual
        )

    except Exception as e:
        logger.error(f"❌ Mains answer generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
