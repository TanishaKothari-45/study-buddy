"""
Example usage of the generic GeminiClient and GeminiCacheManager.
"""
import asyncio
from pydantic import BaseModel
from typing import List
from gemini_client import GeminiClient
from gemini_cache_manager import GeminiCacheManager
import settings_gemini_key


# Example Pydantic schema for structured output
class ProductAttributes(BaseModel):
    """Example schema for product attribute extraction."""
    category: List[str] = []
    voltage: List[str] = []
    power: List[str] = []


async def example_1_simple_text():
    """Example 1: Simple text-based query."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Simple Text Query")
    print("="*60)
    
    client = GeminiClient(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL
    )
    
    response = await client.generate_response(
        user_prompt="What is the capital of France?",
    )
    
    print(f"Response: {response}")


async def example_2_with_pdf():
    """Example 2: Extract information from PDF."""
    print("\n" + "="*60)
    print("EXAMPLE 2: PDF Analysis")
    print("="*60)
    
    client = GeminiClient(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL
    )
    
    response = await client.generate_response(
        user_prompt="Summarize the key information from this document.",
        pdf_path="data/emergency_lighting/pdfs/0000_bodine-gtd20am-specs.pdf",
        system_prompt="You are an expert at analyzing technical documents."
    )
    
    print(f"Response: {response[:200]}...")


async def example_3_structured_output():
    """Example 3: Structured output with Pydantic schema."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Structured Output")
    print("="*60)
    
    client = GeminiClient(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL
    )
    
    response = await client.generate_response(
        user_prompt="Extract product attributes from this specification.",
        pdf_path="data/emergency_lighting/pdfs/0000_bodine-gtd20am-specs.pdf",
        response_schema=ProductAttributes,
        system_prompt="You are an expert at extracting product attributes from technical specifications."
    )
    
    print(f"Structured Response: {response}")


async def example_4_with_caching():
    """Example 4: Using context caching for multiple requests."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Context Caching")
    print("="*60)
    
    # Create cache manager
    cache_mgr = GeminiCacheManager(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL,
        cache_ttl_minutes=60  # 1 hour
    )
    
    # Create a cache with system prompt and few-shot examples
    cache_name = await cache_mgr.create_cache(
        system_prompt="You are an expert at extracting electrical product attributes from technical specifications. Always respond with JSON format.",
        few_shot_examples=[
            {
                "user": "Extract attributes from: LED bulb, 60W, 120V",
                "assistant": '{"category": ["LED Bulb"], "power": ["60W"], "voltage": ["120V"]}'
            }
        ],
        cache_key="product_extraction"
    )
    
    # Create client
    client = GeminiClient(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL
    )
    
    # Make multiple requests using the same cache
    pdf_files = [
        "data/emergency_lighting/pdfs/0000_bodine-gtd20am-specs.pdf",
        "data/emergency_lighting/pdfs/0001_ELCU-100_Catalog_Page.pdf"
    ]
    
    for pdf_path in pdf_files:
        print(f"\nProcessing: {pdf_path.split('/')[-1]}")
        response = await client.generate_response(
            user_prompt="Extract product attributes from this specification.",
            pdf_path=pdf_path,
            cached_content_name=cache_name,  # Use the cache
            response_schema=ProductAttributes
        )
        print(f"Response: {response[:150]}...")
    
    # Clean up cache
    await cache_mgr.delete_cache(cache_name)


async def example_5_concurrent_processing():
    """Example 5: Process multiple files concurrently with semaphore."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Concurrent Processing with Semaphore")
    print("="*60)
    
    # Create semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent requests
    
    client = GeminiClient(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL
    )
    
    pdf_files = [
        "data/emergency_lighting/pdfs/0000_bodine-gtd20am-specs.pdf",
        "data/emergency_lighting/pdfs/0001_ELCU-100_Catalog_Page.pdf",
        "data/emergency_lighting/pdfs/0002_elv-h.pdf",
    ]
    
    async def process_with_semaphore(pdf_path):
        async with semaphore:
            print(f"Processing: {pdf_path.split('/')[-1]}")
            response = await client.generate_response(
                user_prompt="Provide a brief summary of this product.",
                pdf_path=pdf_path
            )
            return {
                "file": pdf_path.split('/')[-1],
                "summary": response[:100] + "..."
            }
    
    # Process all files concurrently
    tasks = [process_with_semaphore(pdf) for pdf in pdf_files]
    results = await asyncio.gather(*tasks)
    
    print("\nResults:")
    for result in results:
        print(f"- {result['file']}: {result['summary']}")


async def example_6_with_image():
    """Example 6: Analyze an image."""
    print("\n" + "="*60)
    print("EXAMPLE 6: Image Analysis")
    print("="*60)
    
    client = GeminiClient(
        api_key=settings_gemini_key.gemini_api_key,
        model_name=settings_gemini_key.GEMINI_MODEL
    )
    
    # Note: You would need to have an image file available
    # This is just a demonstration of the API
    print("Note: This example requires an image file.")
    print("Usage would be:")
    print("""
    response = await client.generate_response(
        user_prompt="Describe what you see in this image.",
        image_path="path/to/image.jpg"
    )
    """)


async def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("GEMINI CLIENT EXAMPLES")
    print("="*60)
    
    # Run examples
    await example_1_simple_text()
    
    # Uncomment to run other examples:
    # await example_2_with_pdf()
    # await example_3_structured_output()
    # await example_4_with_caching()
    # await example_5_concurrent_processing()
    # await example_6_with_image()
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
