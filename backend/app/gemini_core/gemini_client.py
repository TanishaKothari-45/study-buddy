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
            http_options=types.HttpOptions(timeout=timeout)
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
                config_dict["response_mime_type"] = "application/json"
                config_dict["response_schema"] = response_schema
            
            if system_prompt:
                config_dict["system_instruction"] = system_prompt
            
            generation_config = types.GenerateContentConfig(**config_dict)
            
            # Retry loop for transient errors
            while retry_count <= max_retries:
                try:
                    # Use native async API (timeout configured at client level via http_options)
                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=generation_config
                    )
                    
                    if response and response.text:
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
                        print(f"⚠️  Gemini API error: {e}. Retrying ({retry_count}/{max_retries}) after {wait_time}s...")
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
        user_prompt: str,
        system_prompt: Optional[str] = None,
        text_input: Optional[str] = None,
        temperature: float = 0.0
    ):
        """
        Generate streaming response from Gemini API.
        
        Args:
            user_prompt: The main query/instruction
            system_prompt: Optional system-level instructions
            text_input: Optional text context to include
            temperature: Temperature for response generation
            
        Yields:
            Text chunks as they are generated
        """
        if system_prompt is None:
            system_prompt = self.DEFAULT_SYSTEM_PROMPT
        
        prompt_text = user_prompt
        if text_input:
            prompt_text = f"{user_prompt}\n\nContext:\n{text_input}"
        
        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_prompt
        )
        
        async for chunk in self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=[prompt_text],
            config=config
        ):
            if chunk.text:
                yield chunk.text
    
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
    def validate_api_key(api_key: str) -> bool:
        """
        Validate a Gemini API key using list_models().
        This is a lightweight call that doesn't consume generation quota.
        
        Args:
            api_key: The API key to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            client = genai.Client(api_key=api_key)
            # list_models() is a lightweight metadata call
            models = client.models.list()
            # Just check if we can iterate (validates the key)
            for _ in models:
                break
            return True
        except Exception as e:
            print(f"❌ API Key Validation failed: {e}")
            return False
    
    @staticmethod
    async def validate_api_key_async(api_key: str) -> bool:
        """
        Validate a Gemini API key asynchronously.
        
        Args:
            api_key: The API key to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            client = genai.Client(api_key=api_key)
            # Use async list
            models = await client.aio.models.list()
            async for _ in models:
                break
            return True
        except Exception as e:
            print(f"❌ API Key Validation failed: {e}")
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
