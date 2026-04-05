import asyncio
import io
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel
from google import genai
from google.genai import types


class GeminiClient:
    """
    Native async Gemini client for general-purpose API calls.
    
    Uses google-genai package with client.aio for true async operations.
    Supports deferred work patterns with futures for efficient concurrent processing.
    """
    
    # Default system prompt
    DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant. Analyze the provided content carefully and respond accurately."
    
    # Default timeout in seconds
    DEFAULT_TIMEOUT = 120.0
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-pro",
        timeout: float = DEFAULT_TIMEOUT
    ):
        """
        Initialize the Gemini client.
        
        Args:
            api_key: Google AI API key
            model_name: Gemini model to use (default: gemini-2.5-pro)
            timeout: Request timeout in seconds (default: 120.0)
        """
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        
        # Configure client with timeout via http_options
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000))
        )
    
    async def generate_response(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        text_input: Optional[str] = None,
        image_path: Optional[Union[str, List[str]]] = None,
        pdf_path: Optional[Union[str, List[str]]] = None,
        image_bytes: Optional[Union[bytes, List[bytes]]] = None,
        image_futures: Optional[List[asyncio.Future]] = None,
        response_schema: Optional[BaseModel] = None,
        temperature: float = 0.0,
        cached_content_name: Optional[str] = None,
        use_google_search: bool = False,
        max_retries: int = 2
    ) -> str:
        """
        Generate response from Gemini API with native async support.
        
        Args:
            user_prompt: The main query/instruction (required)
            system_prompt: Optional system-level instructions (default provided if None)
            text_input: Optional text context to include
            image_path: Optional path to image file (or list of image files)
            pdf_path: Optional path to PDF file (or list of PDF files)
            image_bytes: Optional image bytes (or list of image bytes) for in-memory images
            image_futures: Optional list of futures that resolve to PIL.Image or bytes
                          (enables deferred work pattern for concurrent downloads)
            response_schema: Optional Pydantic model for structured output
            temperature: Temperature for response generation (default: 0.0)
            cached_content_name: Optional cache name to use for context caching
            max_retries: Maximum retry attempts for transient errors (default: 2)
            
        Returns:
            Response text (JSON string if response_schema provided, otherwise plain text)
            
        Example with futures (deferred work pattern):
            async def download_image(session, url):
                async with session.get(url) as resp:
                    return await resp.read()
            
            # Queue downloads as futures - actual download starts when generate is called
            image_futures = [asyncio.create_task(download_image(session, url)) for url in urls]
            response = await client.generate_response(
                user_prompt="Describe these images",
                image_futures=image_futures
            )
        """
        uploaded_files = []
        retry_count = 0
        
        try:
            # Use default system prompt if none provided
            if system_prompt is None:
                system_prompt = self.DEFAULT_SYSTEM_PROMPT
            
            # Build contents list
            contents = []
            
            # Add text prompt (with optional context)
            prompt_text = user_prompt
            if text_input:
                prompt_text = f"{user_prompt}\n\nContext:\n{text_input}"
            
            contents.append(prompt_text)
            
            # Handle PDF files - upload to Files API
            if pdf_path:
                pdf_paths = [pdf_path] if isinstance(pdf_path, str) else pdf_path
                for path in pdf_paths:
                    uploaded_file = await self._upload_file_async(path, "application/pdf")
                    uploaded_files.append(uploaded_file)
                    contents.append(uploaded_file['file_obj'])
            
            # Handle image paths - upload to Files API
            if image_path:
                image_paths = [image_path] if isinstance(image_path, str) else image_path
                for path in image_paths:
                    mime_type = self._get_image_mime_type(path)
                    uploaded_file = await self._upload_file_async(path, mime_type)
                    uploaded_files.append(uploaded_file)
                    contents.append(uploaded_file['file_obj'])
            
            # Handle image bytes (in-memory images)
            if image_bytes:
                bytes_list = [image_bytes] if isinstance(image_bytes, bytes) else image_bytes
                for img_bytes in bytes_list:
                    # Create inline data part
                    part = types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/jpeg"  # Default to JPEG, could be detected
                    )
                    contents.append(part)
            
            # Handle image futures (deferred work pattern)
            # This allows chaining futures so downloads only start when generation is scheduled
            if image_futures:
                for future in image_futures:
                    img_data = await future
                    # Handle both PIL.Image and bytes
                    if hasattr(img_data, 'save'):
                        # PIL.Image - convert to bytes
                        buffer = io.BytesIO()
                        img_data.save(buffer, format='JPEG')
                        img_bytes = buffer.getvalue()
                    else:
                        img_bytes = img_data
                    
                    part = types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/jpeg"
                    )
                    contents.append(part)
            
            # Build generation config
            config_dict = {
                "temperature": temperature,
            }
            
            if response_schema:
                # If it's a Pydantic model class, convert to JSON schema dict
                if hasattr(response_schema, 'model_json_schema'):
                    response_schema = response_schema.model_json_schema()
                
                # Clean schema recursively to remove keys Gemini doesn't support
                def clean_schema(obj):
                    if isinstance(obj, dict):
                        # Remove keys that cause Gemini API to fail
                        obj.pop('additionalProperties', None)
                        obj.pop('title', None)
                        obj.pop('default', None)
                        
                        for v in obj.values():
                            clean_schema(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            clean_schema(item)
                
                # Clean if it's a dict now
                if isinstance(response_schema, dict):
                    clean_schema(response_schema)
                
                config_dict["response_mime_type"] = "application/json"
                config_dict["response_schema"] = response_schema
            
            if system_prompt:
                config_dict["system_instruction"] = system_prompt
            
            if use_google_search:
                config_dict["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            
            generation_config = types.GenerateContentConfig(**config_dict)
            
            # Retry loop for transient errors
            while retry_count <= max_retries:
                try:
                    # Use native async API (timeout configured at client level via http_options in __init__)
                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=generation_config
                    )
                    
                    if response and response.text:
                        # Log grounding metadata for visibility (Google Search tool results)
                        try:
                            if hasattr(response, 'candidates') and response.candidates:
                                candidate = response.candidates[0]
                                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata is not None:
                                    metadata = candidate.grounding_metadata
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.info("🌐 [GEMINI] Grounding Metadata found (Google Search Tool active)")
                                    
                                    # 1. Log Search Queries (from SDK metadata)
                                    sdk_queries = []
                                    try:
                                        if hasattr(metadata, 'web_search_queries') and metadata.web_search_queries:
                                            sdk_queries = metadata.web_search_queries
                                        elif hasattr(metadata, 'retrieval_queries') and metadata.retrieval_queries:
                                            sdk_queries = metadata.retrieval_queries
                                        elif hasattr(metadata, 'search_entry_point') and hasattr(metadata.search_entry_point, 'sdk_queries') and metadata.search_entry_point.sdk_queries:
                                            sdk_queries = metadata.search_entry_point.sdk_queries
                                        
                                        if sdk_queries:
                                            logger.info(f"🔍 [GEMINI] SDK Search Queries: {sdk_queries}")
                                    except Exception as e:
                                        logger.debug(f"Error extracting SDK queries: {e}")
                                    
                                    # 2. Extract Internal Steps from Text (Topics, Queries, Findings)
                                    import re
                                    import json
                                    
                                    steps = {}
                                    try:
                                        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response.text, re.DOTALL)
                                        if not json_match:
                                            json_match = re.search(r'(\{.*\})', response.text, re.DOTALL)
                                        
                                        if json_match:
                                            full_json = json.loads(json_match.group(1))
                                            steps = full_json.get("intermediate_steps", {})
                                    except: pass

                                    def extract_list(key, text):
                                        pattern = rf'[\"\']?{key}[\"\']?\s*:\s*\[(.*?)\]'
                                        match = re.search(pattern, text, re.DOTALL)
                                        if match:
                                            try:
                                                raw = match.group(1).replace('\n', ' ').strip()
                                                items = [i.strip().strip('\"\'') for i in raw.split(',') if i.strip()]
                                                return items
                                            except: return []
                                        return []

                                    topics = steps.get("topics") or extract_list("topics", response.text)
                                    if topics: logger.info(f"📝 [GEMINI] Step 1 Topics: {topics}")
                                    
                                    queries = steps.get("search_queries") or extract_list("search_queries", response.text)
                                    if queries: logger.info(f"🔍 [GEMINI] Step 2 Search Queries (from text): {queries}")

                                    findings = steps.get("research_findings") or extract_list("research_findings", response.text)
                                    if findings:
                                        logger.info(f"🗞️ [GEMINI] Step 2.5 Research Findings:")
                                        for f in findings: logger.info(f"      • {f}")
                                    
                                    # 3. Log Grounding Chunks (Tool Output)
                                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks is not None:
                                        logger.info(f"📊 [GEMINI] Received {len(metadata.grounding_chunks)} search results")
                                        if len(metadata.grounding_chunks) == 0:
                                            logger.info("   ⚠️ Grounding chunks list is empty")
                                        for i, chunk in enumerate(metadata.grounding_chunks, 1):
                                            if hasattr(chunk, 'web') and chunk.web:
                                                title = getattr(chunk.web, 'title', 'No Title')
                                                uri = getattr(chunk.web, 'uri', 'No URI')
                                                logger.info(f"   📰 Result {i}: {title}")
                                                logger.info(f"      🔗 {uri}")
                                            elif hasattr(chunk, 'text') and chunk.text:
                                                logger.info(f"   📄 Result {i} (Text): {chunk.text[:200]}...")
                                            else:
                                                logger.info(f"   ❓ Result {i}: {chunk}")
                                    else:
                                        logger.debug("📊 [GEMINI] No grounding chunks found in metadata object")

                                    # Check search_entry_point
                                    if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point:
                                         logger.info("🔍 [GEMINI] Search entry point found (UI elements available)")
                                    
                                    # 4. Log Grounding Supports
                                    try:
                                        if hasattr(metadata, 'grounding_supports') and metadata.grounding_supports:
                                            logger.info(f"✨ [GEMINI] Response has {len(metadata.grounding_supports)} grounded segments")
                                    except: pass
                        except Exception as log_err:
                            import logging
                            logging.getLogger(__name__).warning(f"⚠️ Failed to log grounding metadata: {log_err}")

                        return response.text
                    else:
                        raise Exception("Empty response from Gemini API")
                
                except Exception as e:
                    error_str = str(e).lower()
                    
                    # Don't retry quota errors (429) - they need time, not retries
                    if '429' in error_str or 'quota' in error_str or 'resource_exhausted' in error_str:
                        raise
                    
                    # Don't retry auth errors (401, 403)
                    if '401' in error_str or '403' in error_str or 'api key' in error_str or 'permission' in error_str:
                        raise
                    
                    # Don't retry invalid request errors (400)
                    if '400' in error_str or 'invalid' in error_str:
                        raise
                    
                    # Retry transient errors (timeouts, 500s, network issues)
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = retry_count * 2  # Exponential-ish backoff: 2s, 4s, 6s
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"⚠️  Gemini API error: {e}. Retrying ({retry_count}/{max_retries}) after {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        raise
            
            # Should not reach here, but just in case
            raise Exception("Max retries exceeded")
            
        finally:
            # Clean up uploaded files asynchronously
            if uploaded_files:
                cleanup_tasks = [
                    self._delete_file_async(f['name']) 
                    for f in uploaded_files
                ]
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    async def generate_response_streaming(
        self,
        text_input: Optional[str] = None,
        temperature: float = 0.0,
        use_google_search: bool = False,
        system_prompt: Optional[str] = None
    ):
        """
        Generate streaming response from Gemini API.
        
        Args:
            text_input: The main text/prompt to send
            temperature: Temperature for response generation
            use_google_search: Whether to enable Google Search tool
            system_prompt: Optional system-level instructions
            
        Yields:
            Text chunks as they are generated
        """
        if system_prompt is None:
            system_prompt = self.DEFAULT_SYSTEM_PROMPT
        
        if not text_input:
            raise ValueError("text_input is required for streaming")
        
        config_dict = {
            "temperature": temperature,
            "system_instruction": system_prompt
        }
        
        if use_google_search:
            config_dict["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            
        config = types.GenerateContentConfig(**config_dict)
        
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Use non-streaming API and simulate streaming by chunking the response
            # This is more reliable than trying to use generate_content_stream which may not be available
            logger.debug(f"📝 Generating response for streaming (model: {self.model_name})")
            
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[text_input],
                config=config
            )
            
            if not response:
                logger.warning("⚠️ Empty response from Gemini")
                return
            
            if not response.text:
                logger.warning("⚠️ Response has no text content")
                return
            
            # Simulate streaming by yielding in chunks
            text = response.text
            chunk_size = 30  # Characters per chunk for smooth streaming effect
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                if chunk:  # Only yield non-empty chunks
                    yield chunk
                    # Small delay to simulate real streaming
                    await asyncio.sleep(0.02)
                    
        except Exception as e:
            logger.error(f"❌ Streaming error: {e}", exc_info=True)
            raise
    
    def create_chat_session(self, system_instruction: str):
        """
        Create a new chat session with system instruction.
        
        Note: This uses the sync API for compatibility with existing code.
        For async chat, use create_async_chat_session().
        
        Args:
            system_instruction: System-level instructions for the chat
            
        Returns:
            Chat session object
        """
        # Use sync client for chat sessions (backward compatibility)
        return self.client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
    
    async def create_async_chat_session(self, system_instruction: str):
        """
        Create a new async chat session with system instruction.
        
        Args:
            system_instruction: System-level instructions for the chat
            
        Returns:
            Async chat session object
        """
        return await self.client.aio.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
    
    def send_chat_message(self, chat, message: str) -> str:
        """
        Send a message to an existing chat session (sync).
        
        Args:
            chat: Chat session object from create_chat_session()
            message: Message to send
            
        Returns:
            Response text from the model
        """
        response = chat.send_message(message)
        return response.text
    
    async def send_chat_message_async(self, chat, message: str) -> str:
        """
        Send a message to an existing async chat session.
        
        Args:
            chat: Async chat session object from create_async_chat_session()
            message: Message to send
            
        Returns:
            Response text from the model
        """
        response = await chat.send_message_async(message)
        return response.text

    async def search_and_summarise(
        self,
        queries: list,
        context_hint: str = "",
        temperature: float = 0.3,
    ) -> str:
        """
        Run Google Search for CA-flagged questions and return a summarised text block.

        Uses the first query as the primary search prompt (use_google_search=True)
        and appends remaining queries to the prompt as supplementary context.

        Args:
            queries:      List of search query strings (1-3 recommended)
            context_hint: Hint appended to the system prompt (e.g. subject/concept)
            temperature:  Lower = more factual (default 0.3)

        Returns:
            Summarised text suitable for injection into the generation prompt.
        """
        if not queries:
            return ""

        primary_query = queries[0]
        extra = " | ".join(queries[1:]) if len(queries) > 1 else ""

        user_prompt = (
            f"Search for current, factual information about: {primary_query}\n"
            + (f"Also retrieve: {extra}\n" if extra else "")
            + "\nSummarise the most recent and relevant facts in 200-300 words. "
            "Prioritise information from the last 6 months. "
            "Focus on facts useful for a UPSC Prelims question. No opinion, no padding."
        )
        system_prompt = (
            f"You are a UPSC current affairs analyst. {context_hint}. "
            "Return only factual, verifiable information from search results. "
            "Prefer the most recent results available."
        )

        try:
            result = await self.generate_response(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                use_google_search=True,
            )
            return result or ""
        except Exception:
            return ""

    async def _upload_file_async(self, file_path: str, mime_type: str) -> Dict[str, Any]:
        """
        Upload a file to Gemini Files API using native async.
        
        Args:
            file_path: Path to the file
            mime_type: MIME type of the file
            
        Returns:
            Dict with file name and URI
        """
        # Use async file upload
        file_obj = await self.client.aio.files.upload(
            file=file_path,
            config=types.UploadFileConfig(mime_type=mime_type)
        )
        
        # Wait for processing with async polling
        max_wait = 60  # Max 60 seconds
        wait_time = 0
        while file_obj.state.name == "PROCESSING" and wait_time < max_wait:
            await asyncio.sleep(1)
            wait_time += 1
            file_obj = await self.client.aio.files.get(name=file_obj.name)
        
        if file_obj.state.name == "PROCESSING":
            raise Exception(f"File processing timeout after {max_wait}s: {file_path}")
        
        if file_obj.state.name == "FAILED":
            raise Exception(f"File processing failed: {file_path}")
            
        return {
            'name': file_obj.name,
            'uri': file_obj.uri,
            'mime_type': mime_type,
            'file_obj': file_obj
        }
    
    async def _delete_file_async(self, file_name: str):
        """
        Delete an uploaded file from Gemini Files API.
        
        Args:
            file_name: Name of the file to delete
        """
        try:
            await self.client.aio.files.delete(name=file_name)
        except Exception:
            pass  # Ignore deletion errors
            
    def _get_image_mime_type(self, file_path: str) -> str:
        """
        Get MIME type for image file based on extension.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            MIME type string
        """
        extension = file_path.lower().split('.')[-1]
        mime_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp',
            'bmp': 'image/bmp',
            'tiff': 'image/tiff',
            'tif': 'image/tiff'
        }
        return mime_types.get(extension, 'image/jpeg')
    
    @staticmethod
    def validate_api_key(api_key: str, max_retries: int = 3) -> bool:
        """
        Validate a Gemini API key using list_models().
        This is a lightweight call that doesn't consume generation quota.
        
        Includes retry logic to handle transient network/API issues.
        
        Args:
            api_key: The API key to validate
            max_retries: Number of retry attempts for transient failures
            
        Returns:
            True if valid, False otherwise
        """
        import time
        
        for attempt in range(max_retries):
            try:
                client = genai.Client(api_key=api_key)
                # list_models() is a lightweight metadata call
                models = client.models.list()
                # Just check if we can iterate (validates the key)
                for _ in models:
                    break
                return True
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a definitive auth error (invalid key)
                # These should NOT be retried
                if any(keyword in error_str for keyword in [
                    'invalid api key',
                    'api key not valid',
                    'api_key_invalid',
                    'permission denied',
                    'unauthenticated',
                    '401',
                    '403',
                ]):
                    print(f"❌ API Key Validation failed (invalid key): {e}")
                    return False
                
                # For transient errors (network, timeout, rate limit), retry
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 0.5  # 0.5s, 1s, 1.5s
                    print(f"⚠️ API Key Validation attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    print(f"❌ API Key Validation failed after {max_retries} attempts: {e}")
                    return False
        
        return False
    
    @staticmethod
    async def validate_api_key_async(api_key: str, max_retries: int = 3) -> bool:
        """
        Validate a Gemini API key asynchronously.
        
        Includes retry logic to handle transient network/API issues.
        
        Args:
            api_key: The API key to validate
            max_retries: Number of retry attempts for transient failures
            
        Returns:
            True if valid, False otherwise
        """
        import asyncio
        
        for attempt in range(max_retries):
            try:
                client = genai.Client(api_key=api_key)
                # Use async list
                models = await client.aio.models.list()
                async for _ in models:
                    break
                return True
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if this is a definitive auth error (invalid key)
                # These should NOT be retried
                if any(keyword in error_str for keyword in [
                    'invalid api key',
                    'api key not valid',
                    'api_key_invalid',
                    'permission denied',
                    'unauthenticated',
                    '401',
                    '403',
                ]):
                    print(f"❌ API Key Validation failed (invalid key): {e}")
                    return False
                
                # For transient errors (network, timeout, rate limit), retry
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 0.5  # 0.5s, 1s, 1.5s
                    print(f"⚠️ API Key Validation attempt {attempt + 1} failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ API Key Validation failed after {max_retries} attempts: {e}")
                    return False
        
        return False


# Utility function for concurrent image processing (as shown in user's example)
async def process_images_concurrently(
    client: GeminiClient,
    prompt: str,
    image_futures: List[asyncio.Future],
    system_prompt: Optional[str] = None
) -> str:
    """
    Process multiple images concurrently using the deferred work pattern.
    
    This utility function demonstrates how to chain futures together
    so that image downloads only start when the generation is scheduled.
    
    Args:
        client: GeminiClient instance
        prompt: The prompt to use for generation
        image_futures: List of futures that resolve to PIL.Image or bytes
        system_prompt: Optional system prompt
        
    Returns:
        Generated response text
        
    Example:
        async with aiohttp.ClientSession() as session:
            async def download_image(url):
                async with session.get(url) as resp:
                    buffer = io.BytesIO()
                    buffer.write(await resp.read())
                    return PIL.Image.open(buffer)
            
            # Create download tasks
            futures = [asyncio.create_task(download_image(url)) for url in image_urls]
            
            # Process all images with single API call
            result = await process_images_concurrently(
                client=gemini_client,
                prompt="Describe each image",
                image_futures=futures
            )
    """
    return await client.generate_response(
        user_prompt=prompt,
        system_prompt=system_prompt,
        image_futures=image_futures
    )
