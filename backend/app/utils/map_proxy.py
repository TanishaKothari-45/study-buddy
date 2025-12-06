"""
Map generation proxy endpoint.

This module provides utilities to:
1. Call the Node.js map generation microservice
2. Parse map-json blocks from LLM output
3. Generate and embed SVG maps in markdown
4. Cache generated maps in Redis
"""

import httpx
import re
import json
import logging
import base64
from typing import Optional, Dict, Any

# Configure logging
logger = logging.getLogger(__name__)

# Map service configuration
MAP_SERVICE_URL = "http://localhost:3001"
MAP_SERVICE_TIMEOUT = 30.0  # seconds


async def generate_map_from_json(map_data: Dict[str, Any]) -> str:
    """
    Generate map with Redis caching.
    
    Flow:
    1. Check Redis cache for map (based on map spec hash)
    2. If HIT: Return cached SVG
    3. If MISS: Call Node.js service -> Cache result -> Return SVG
    
    Args:
        map_data: Map configuration JSON
        
    Returns:
        Markdown image string with base64-embedded SVG
        
    Raises:
        Exception: If map generation fails
    """
    try:
        from ..utils.cache_manager import get_cache_manager
        cache = get_cache_manager()
        
        title = map_data.get('title', 'Map')
        logger.info(f"🗺️  Generating map: {title}")
        logger.debug(f"Map config: {json.dumps(map_data, indent=2)}")
        
        # Check cache first
        if cache and cache.enabled:
            cached_svg_base64 = cache.get_cached_map(map_data)
            
            if cached_svg_base64:
                logger.info(f"🎯 [MAP CACHE HIT] Using cached map for '{title}'")
                return f"![{title}](data:image/svg+xml;base64,{cached_svg_base64})"
            else:
                logger.info(f"❌ [MAP CACHE MISS] Generating map for '{title}'")
        
        # Cache MISS - call Node.js service
        async with httpx.AsyncClient(timeout=MAP_SERVICE_TIMEOUT) as client:
            response = await client.post(
                f"{MAP_SERVICE_URL}/generate-map",
                json=map_data
            )
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"✅ Map generated successfully")
            logger.debug(f"Map hash: {result.get('hash')}, Service cached: {result.get('cached')}")
            
            # Get SVG base64 from response
            svg_base64 = result['svg_base64']
            
            # Store in Redis cache
            if cache and cache.enabled:
                cache.set_cached_map(map_data, svg_base64)
            
            return f"![{title}](data:image/svg+xml;base64,{svg_base64})"
            
    except ImportError:
        # Cache manager not available - proceed without caching
        logger.warning("⚠️  Cache manager not available, proceeding without map caching")
        # Fall through to generate without cache
        pass
    except httpx.TimeoutException as e:
        logger.error(f"❌ Map generation timeout: {str(e)}")
        return f"\n\n**[Map generation timed out]**\n\n"
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP {e.response.status_code}"
        try:
            error_json = e.response.json()
            if 'details' in error_json:
                error_msg += f" - {error_json['details']}"
            elif 'error' in error_json:
                error_msg += f" - {error_json['error']}"
        except:
            error_msg += f" - {e.response.text[:100]}"
            
        logger.error(f"❌ Map generation failed: {error_msg}")
        return f"\n\n**[Map generation failed: {error_msg}]**\n\n"
    except Exception as e:
        logger.error(f"❌ Map generation error: {str(e)}", exc_info=True)
        return f"\n\n**[Map generation failed: {str(e)}]**\n\n"


async def parse_and_generate_maps(content: str) -> str:
    """
    Find map-json blocks in content and replace with generated maps.
    
    Args:
        content: Markdown content with potential map-json blocks
        
    Returns:
        Content with map-json blocks replaced by SVG images
    """
    logger.info("🔍 Parsing content for map-json blocks")
    
    # Pattern to match map-json code blocks
    pattern = r'```map-json\s*\n(.*?)\n```'
    
    matches = list(re.finditer(pattern, content, flags=re.DOTALL))
    
    if not matches:
        logger.info("ℹ️  No map-json blocks found")
        return content
    
    logger.info(f"📍 Found {len(matches)} map-json block(s)")
    
    # Process matches in reverse order to preserve indices
    for i, match in enumerate(reversed(matches), 1):
        try:
            map_json_str = match.group(1)
            logger.debug(f"Processing map block {i}/{len(matches)}")
            
            # Parse JSON
            try:
                map_data = json.loads(map_json_str)
                # Log the map data to debug region issues
                logger.info(f"📋 Map JSON block {i}: region='{map_data.get('region')}', title='{map_data.get('title')}'")
                logger.debug(f"Full map JSON: {json.dumps(map_data, indent=2)}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Invalid JSON in map block {i}: {str(e)}")
                logger.debug(f"Invalid JSON: {map_json_str[:200]}...")
                # Replace with error message
                content = content[:match.start()] + \
                         f"\n\n**[Invalid map JSON: {str(e)}]**\n\n" + \
                         content[match.end():]
                continue
            
            # Validate map data
            if not isinstance(map_data, dict) or map_data.get('type') != 'map':
                logger.warning(f"⚠️  Map block {i} missing 'type': 'map'")
            
            # Generate map
            map_markdown = await generate_map_from_json(map_data)
            
            # Replace the map-json block with the generated map
            content = content[:match.start()] + map_markdown + content[match.end():]
            
            logger.info(f"✅ Replaced map block {i}/{len(matches)}")
            
        except Exception as e:
            logger.error(f"❌ Error processing map block {i}: {str(e)}", exc_info=True)
            # Replace with error message
            content = content[:match.start()] + \
                     f"\n\n**[Map processing error: {str(e)}]**\n\n" + \
                     content[match.end():]
    
    logger.info(f"✅ Completed map processing: {len(matches)} block(s) processed")
    return content


async def check_map_service_health() -> bool:
    """
    Check if the map generation service is running.
    
    Returns:
        True if service is healthy, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{MAP_SERVICE_URL}/health")
            response.raise_for_status()
            result = response.json()
            
            is_healthy = result.get('status') == 'ok'
            if is_healthy:
                logger.info("✅ Map service is healthy")
            else:
                logger.warning(f"⚠️  Map service returned unexpected status: {result}")
            
            return is_healthy
            
    except Exception as e:
        logger.error(f"❌ Map service health check failed: {str(e)}")
        return False
