"""
domain_enricher.py
Enriches existing chunks with:
- major_domain (broad subject area)
- sub_domain (specific topic category)
- micro_topic (fine-grained concept)
Optionally predicts sub_topics when multiple ideas exist in one chunk.
"""

import json
import logging
from typing import List, Dict, Any
from openai import OpenAI
from tqdm import tqdm
import time

logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
MODEL = "gpt-4o-mini"
BATCH_SIZE = 5  # classify 5 chunks per API call for efficiency
OUTPUT_FILE = "enriched_chunks.json"

SYSTEM_PROMPT = """
You are a UPSC Geography domain expert. 
Given a chunk of study material, classify it hierarchically.

For each chunk, return a JSON object with:
{
  "major_domain": one of ["Physical Geography", "Human Geography", "Indian Geography", "World Geography"],
  "sub_domain": a specific topic within the major_domain (like "Climatology", "Geomorphology", "Population Geography", "Indian Agriculture"),
  "micro_topic": the most specific concept or phenomenon (like "Monsoon", "Jet Streams", "Soil Erosion"),
  "sub_topics": [optional list of smaller ideas or examples if present]
}

Guidelines:
- Base your classification strictly on the text meaning.
- Use concise, syllabus-aligned terms.
- If unsure about the micro_topic, return "General Concepts".
Return only valid JSON — no explanations.
"""

def classify_chunks(chunks: List[Dict[str, Any]], client: OpenAI) -> List[Dict[str, Any]]:
    enriched_chunks = []

    for i in tqdm(range(0, len(chunks), BATCH_SIZE)):
        batch = chunks[i:i+BATCH_SIZE]

        # Combine all chunks into a single user message
        combined_text = "\n\n".join(
            [f"CHUNK {i+j+1}:\n{c['content'][:2000]}" for j, c in enumerate(batch)]
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": combined_text}
        ]

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.2
            )
            output = response.choices[0].message.content

            # Attempt to parse each JSON object inside output
            try:
                # Split and parse: GPT will often return list of JSONs
                json_objects = json.loads(output)
                if isinstance(json_objects, dict):
                    json_objects = [json_objects]
            except json.JSONDecodeError:
                logger.warning(f"⚠️ Could not parse GPT output directly. Raw:\n{output[:400]}")
                json_objects = []

            for j, chunk in enumerate(batch):
                classification = json_objects[j] if j < len(json_objects) else {}
                enriched_meta = chunk["metadata"].copy()
                enriched_meta.update({
                    "major_domain": classification.get("major_domain"),
                    "sub_domain": classification.get("sub_domain"),
                    "micro_topic": classification.get("micro_topic"),
                    "sub_topics": classification.get("sub_topics", [])
                })
                enriched_chunks.append({
                    "content": chunk["content"],
                    "metadata": enriched_meta
                })

        except Exception as e:
            logger.error(f"❌ Batch {i//BATCH_SIZE+1} failed: {e}")
            # Retry after short delay
            time.sleep(3)
            continue

    return enriched_chunks


def enrich_file(input_path: str, output_path: str = OUTPUT_FILE):
    client = OpenAI()

    # Load existing chunks
    with open(input_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    logger.info(f"📚 Loaded {len(chunks)} chunks from {input_path}")

    enriched_chunks = classify_chunks(chunks, client)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched_chunks, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Saved {len(enriched_chunks)} enriched chunks → {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich chunks with domain/subdomain/micro-topic classification")
    parser.add_argument("--input", required=True, help="Path to input chunks JSON file")
    parser.add_argument("--output", default=OUTPUT_FILE, help="Path to save enriched output")
    args = parser.parse_args()

    enrich_file(args.input, args.output)
