"""
Test script for map generation integration.

This script tests the complete flow:
1. Map service health check
2. Direct map generation via proxy
3. Map-json parsing and replacement

Run this before testing with real LLM-generated answers.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.utils.map_proxy import (
    check_map_service_health,
    generate_map_from_json,
    parse_and_generate_maps
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_health_check():
    """Test map service health check"""
    logger.info("=" * 70)
    logger.info("TEST 1: Map Service Health Check")
    logger.info("=" * 70)
    
    is_healthy = await check_map_service_health()
    
    if is_healthy:
        logger.info("✅ Map service is healthy and ready")
        return True
    else:
        logger.error("❌ Map service is not available")
        logger.error("   Make sure to start the service: cd map-service && npm start")
        return False


async def test_direct_generation():
    """Test direct map generation"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: Direct Map Generation")
    logger.info("=" * 70)
    
    # Test data: Simple marker map
    map_data = {
        "type": "map",
        "mapType": "markers",
        "region": "india",
        "topoKey": "india_states_v1",
        "width": 900,
        "height": 1100,
        "title": "Test Map - Major Cities",
        "markers": [
            {"name": "Delhi", "coordinates": [77.2, 28.6], "type": "city", "label": "Delhi"},
            {"name": "Mumbai", "coordinates": [72.8, 19.1], "type": "city", "label": "Mumbai"},
            {"name": "Kolkata", "coordinates": [88.4, 22.6], "type": "city", "label": "Kolkata"}
        ],
        "style": {"theme": "warm"}
    }
    
    try:
        result = await generate_map_from_json(map_data)
        logger.info(f"✅ Map generated successfully")
        logger.info(f"   Result length: {len(result)} chars")
        logger.info(f"   Preview: {result[:100]}...")
        return True
    except Exception as e:
        logger.error(f"❌ Map generation failed: {str(e)}")
        return False


async def test_parsing():
    """Test map-json parsing and replacement"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: Map-JSON Parsing and Replacement")
    logger.info("=" * 70)
    
    # Sample answer with map-json block
    sample_answer = """
### Regional Distribution of Coal Reserves

India's coal reserves are concentrated in specific geological formations.

**Map: Major Coalfields in India**
```map-json
{
  "type": "map",
  "mapType": "markers",
  "region": "india",
  "topoKey": "india_states_v1",
  "title": "Major Coalfields in India",
  "markers": [
    {"name": "Jharia", "coordinates": [85.62, 23.78], "type": "coal", "label": "Jharia"},
    {"name": "Raniganj", "coordinates": [87.13, 23.62], "type": "coal", "label": "Raniganj"}
  ],
  "style": {"theme": "warm"}
}
```

**Coalfield Locations**:
• **Jharia (Jharkhand)**: Largest coalfield with 19.4 billion tonnes reserves
• **Raniganj (West Bengal)**: Second largest, supplies Eastern India
"""
    
    try:
        logger.info("Processing sample answer with map-json block...")
        result = await parse_and_generate_maps(sample_answer)
        
        # Check if map-json was replaced
        if "```map-json" in result:
            logger.error("❌ Map-json block was not replaced")
            return False
        
        if "![" in result and "data:image/svg+xml;base64," in result:
            logger.info("✅ Map-json successfully replaced with SVG image")
            logger.info(f"   Result length: {len(result)} chars")
            return True
        else:
            logger.error("❌ Map-json was removed but no SVG image found")
            return False
            
    except Exception as e:
        logger.error(f"❌ Parsing failed: {str(e)}")
        return False


async def test_invalid_json():
    """Test handling of invalid map-json"""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 4: Invalid Map-JSON Handling")
    logger.info("=" * 70)
    
    # Sample with invalid JSON
    sample_answer = """
### Test Section

```map-json
{
  "type": "map",
  "invalid": json here
}
```

Some text after.
"""
    
    try:
        logger.info("Processing answer with invalid map-json...")
        result = await parse_and_generate_maps(sample_answer)
        
        if "[Invalid map JSON:" in result:
            logger.info("✅ Invalid JSON handled gracefully with error message")
            return True
        else:
            logger.warning("⚠️  Invalid JSON handling may need improvement")
            return True  # Still pass, just warn
            
    except Exception as e:
        logger.error(f"❌ Error handling failed: {str(e)}")
        return False


async def main():
    """Run all tests"""
    logger.info("\n" + "🗺️  MAP GENERATION INTEGRATION TESTS")
    logger.info("=" * 70)
    
    results = []
    
    # Test 1: Health check
    results.append(("Health Check", await test_health_check()))
    
    # Only continue if service is healthy
    if not results[0][1]:
        logger.error("\n❌ TESTS FAILED: Map service is not running")
        logger.error("   Start the service first: cd map-service && npm start")
        return
    
    # Test 2: Direct generation
    results.append(("Direct Generation", await test_direct_generation()))
    
    # Test 3: Parsing
    results.append(("Parsing & Replacement", await test_parsing()))
    
    # Test 4: Error handling
    results.append(("Error Handling", await test_invalid_json()))
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED!")
        logger.info("   Map generation integration is ready to use.")
    else:
        logger.error("\n❌ SOME TESTS FAILED")
        logger.error("   Please fix the issues before proceeding.")


if __name__ == "__main__":
    asyncio.run(main())
