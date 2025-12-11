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
import xml.etree.ElementTree as ET

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
            
            # Prefer PNG thumbnail if provided (lighter for clients); fallback to SVG
            png_base64 = result.get('png_base64')
            svg_base64 = result['svg_base64']
            logger.debug(f"[MAP] Raw SVG base64 length: {len(svg_base64)}; PNG available: {bool(png_base64)}")
            image_base64 = png_base64 or svg_base64
            mime = "image/png" if png_base64 else "image/svg+xml"
            if not png_base64:
                # Sanitize + normalize labels before embedding SVG
                try:
                    svg_base64 = sanitize_and_normalize_svg(svg_base64)
                    image_base64 = svg_base64
                except Exception as e:
                    logger.warning(f"⚠️  SVG postprocess failed, using raw SVG: {e}")
            
            # Store in Redis cache
            if cache and cache.enabled:
                cache.set_cached_map(map_data, image_base64)
            
            return f"![{title}](data:{mime};base64,{image_base64})"
            
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


def sanitize_and_normalize_svg(svg_base64: str, max_label_len: int = 12, y_offset: float = 8.0) -> str:
    """
    Decode -> sanitize -> truncate labels -> add tooltips -> light de-overlap -> re-encode.
    Keeps latency low and runs server-side to avoid client DOM sanitization.
    """
    svg_text = base64.b64decode(svg_base64).decode("utf-8", errors="ignore")
    
    # Parse XML safely and preserve namespaces
    parser = ET.XMLParser()
    try:
        root = ET.fromstring(svg_text, parser=parser)
    except ET.ParseError as e:
        snippet = svg_text[:500].replace("\n", " ") if svg_text else ""
        logger.error(f"❌ SVG parse error: {e}. Snippet: {snippet}")
        raise

    # Preserve or add default SVG namespace to avoid ns0 prefixes
    if isinstance(root.tag, str) and root.tag.startswith("{"):
        svg_ns = root.tag.split("}", 1)[0].strip("{")
    else:
        svg_ns = "http://www.w3.org/2000/svg"
        root.tag = f"{{{svg_ns}}}{root.tag}"
    ET.register_namespace("", svg_ns)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    # Ensure xmlns attributes exist (helps some renderers)
    if "xmlns" not in root.attrib:
        root.set("xmlns", svg_ns)
    if "xmlns:xlink" not in root.attrib:
        root.set("xmlns:xlink", "http://www.w3.org/1999/xlink")
    
    # Namespace handling helper
    def strip_ns(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag
    
    # Remove unsafe elements and attributes
    unsafe_tags = {"script", "foreignObject", "iframe", "object", "embed", "image"}

    def prune_unsafe(parent):
        for child in list(parent):
            tag = strip_ns(child.tag)
            if tag in unsafe_tags:
                parent.remove(child)
                continue
            # Drop on* handlers and external hrefs
            to_delete = []
            for attr, val in child.attrib.items():
                if attr.lower().startswith("on"):
                    to_delete.append(attr)
                if attr in ("href", "{http://www.w3.org/1999/xlink}href") and val.startswith("http"):
                    to_delete.append(attr)
            for attr in to_delete:
                child.attrib.pop(attr, None)
            prune_unsafe(child)

    prune_unsafe(root)
    
    # Light label truncation + tooltip + y-offset for overlapping coords
    seen_coords = {}
    for elem in root.iter():
        if strip_ns(elem.tag) != "text":
            continue
        original_text = "".join(elem.itertext()).strip()
        if not original_text:
            continue
        
        # Truncate for display, preserve original in <title>
        display_text = original_text
        if len(display_text) > max_label_len:
            display_text = display_text[: max_label_len - 1] + "..."
        
        # Replace text content
        for child in list(elem):
            elem.remove(child)
        elem.text = display_text
        title_node = ET.SubElement(elem, "title")
        title_node.text = original_text
        
        # Resolve coordinates and nudge if overlapping
        try:
            x = float(elem.attrib.get("x", "nan"))
            y = float(elem.attrib.get("y", "nan"))
            if not (x != x or y != y):  # check for NaN
                key = (round(x, 0), round(y, 0))
                count = seen_coords.get(key, 0)
                if count > 0:
                    elem.set("y", str(y + y_offset * count))
                seen_coords[key] = count + 1
        except Exception:
            # Best-effort; skip offsets if coords missing
            pass
    
    sanitized = ET.tostring(root, encoding="utf-8").decode("utf-8")
    return base64.b64encode(sanitized.encode("utf-8")).decode("utf-8")


async def parse_and_generate_maps(content: str) -> str:
    """
    Find map-json blocks in content and replace with generated maps.
    ALL maps are generated in PARALLEL for better performance.
    
    Args:
        content: Markdown content with potential map-json blocks
        
    Returns:
        Content with map-json blocks replaced by SVG images
    """
    import asyncio
    import time
    
    logger.info("🔍 Parsing content for map-json blocks")
    
    # Pattern to match map-json code blocks
    pattern = r'```map-json\s*\n(.*?)\n```'
    
    matches = list(re.finditer(pattern, content, flags=re.DOTALL))
    
    if not matches:
        logger.info("ℹ️  No map-json blocks found")
        return content
    
    logger.info(f"📍 Found {len(matches)} map-json block(s)")
    
    # Start timing for performance metrics
    parallel_start = time.perf_counter()
    
    # Helper function to process a single map block
    async def process_single_map(match, index):
        """Process a single map block and return (match, result, time)"""
        map_start = time.perf_counter()
        try:
            map_json_str = match.group(1)
            logger.debug(f"Processing map block {index}/{len(matches)}")
            
            # Parse JSON
            try:
                map_data = json.loads(map_json_str)
                logger.info(f"📋 Map JSON block {index}: region='{map_data.get('region')}', title='{map_data.get('title')}'")
                logger.debug(f"Full map JSON: {json.dumps(map_data, indent=2)}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Invalid JSON in map block {index}: {str(e)}")
                map_time = (time.perf_counter() - map_start) * 1000
                return (match, f"\n\n**[Invalid map JSON: {str(e)}]**\n\n", map_time, False)
            
            # Validate map data
            if not isinstance(map_data, dict) or map_data.get('type') != 'map':
                logger.warning(f"⚠️  Map block {index} missing 'type': 'map'")
            
            # Generate map
            map_markdown = await generate_map_from_json(map_data)
            map_time = (time.perf_counter() - map_start) * 1000
            
            logger.info(f"✅ Map block {index} processed in {map_time:.1f}ms")
            return (match, map_markdown, map_time, True)
            
        except Exception as e:
            logger.error(f"❌ Error processing map block {index}: {str(e)}", exc_info=True)
            map_time = (time.perf_counter() - map_start) * 1000
            return (match, f"\n\n**[Map processing error: {str(e)}]**\n\n", map_time, False)
    
    # Process ALL maps in parallel
    logger.info(f"⚡ Processing {len(matches)} map(s) in PARALLEL...")
    map_tasks = [process_single_map(match, i) for i, match in enumerate(reversed(matches), 1)]
    results = await asyncio.gather(*map_tasks)
    
    # Calculate timing metrics
    parallel_total_time = (time.perf_counter() - parallel_start) * 1000
    map_times = [result[2] for result in results]
    sequential_estimate = sum(map_times)
    time_saved = sequential_estimate - parallel_total_time
    successful_maps = sum(1 for result in results if result[3])
    
    # Log performance metrics
    logger.info(f"⏱️  [PERFORMANCE METRICS - Map Generation]:")
    logger.info(f"   • Total maps: {len(matches)}")
    logger.info(f"   • Successful: {successful_maps}, Failed: {len(matches) - successful_maps}")
    logger.info(f"   • Per-map time: avg={sum(map_times)/len(map_times):.1f}ms, min={min(map_times):.1f}ms, max={max(map_times):.1f}ms")
    logger.info(f"   • Total parallel time: {parallel_total_time:.1f}ms")
    logger.info(f"   • Sequential would take: {sequential_estimate:.1f}ms")
    if len(matches) > 1:
        logger.info(f"   • ⚡ TIME SAVED: {time_saved:.1f}ms ({(time_saved/sequential_estimate*100):.0f}% faster)")
    
    # Replace map blocks with generated maps (in reverse order to preserve indices)
    for match, map_markdown, _, _ in results:
        # Replace the map-json block with the generated map
        content = content[:match.start()] + map_markdown + content[match.end():]
    
    logger.info(f"✅ Completed map processing: {len(matches)} block(s) processed in parallel")
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
