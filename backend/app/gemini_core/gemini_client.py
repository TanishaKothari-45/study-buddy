import asyncio
import time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from google import genai


class GeminiClient:
    """Simple async Gemini client for general-purpose API calls."""
    
    # Default system prompt
    DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant. Analyze the provided content carefully and respond accurately."
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-pro"
    ):
        """
        Initialize the Gemini client.
        
        Args:
            api_key: Google AI API key
            model_name: Gemini model to use (default: gemini-2.5-pro)
        """
        self.api_key = api_key
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key)
    
    async def generate_response(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        text_input: Optional[str] = None,
        image_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        response_schema: Optional[BaseModel] = None,
        temperature: float = 0.0,
        cached_content_name: Optional[str] = None,
        max_retries: int = 2
    ) -> str:
        """
        Generate response from Gemini API with optional caching.
        
        Args:
            user_prompt: The main query/instruction (required)
            system_prompt: Optional system-level instructions (default provided if None)
            text_input: Optional text context to include
            image_path: Optional path to image file
            pdf_path: Optional path to PDF file
            response_schema: Optional Pydantic model for structured output
            temperature: Temperature for response generation (default: 0.0)
            cached_content_name: Optional cache name to use for context caching
            max_retries: Maximum number of retry attempts (default: 2)
            
        Returns:
            Response text (JSON string if response_schema provided, otherwise plain text)
        """
        uploaded_file = None
        retry_count = 0
        
        try:
            # Use default system prompt if none provided
            if system_prompt is None:
                system_prompt = self.DEFAULT_SYSTEM_PROMPT
            
            # Upload file if needed (PDF or image)
            if pdf_path:
                uploaded_file = await self._upload_file_async(pdf_path, "application/pdf")
            elif image_path:
                # Detect image mime type
                mime_type = self._get_image_mime_type(image_path)
                uploaded_file = await self._upload_file_async(image_path, mime_type)
            
            # Build content parts
            content_parts = self._build_content_parts(
                user_prompt, text_input, uploaded_file
            )
            
            # Build config
            config = self._build_config(
                response_schema, temperature, cached_content_name
            )
            
            # Make request with retry logic
            while retry_count < max_retries:
                try:
                    response = await self._make_request_async(
                        system_prompt, content_parts, config, cached_content_name
                    )
                    
                    if response and response.text:
                        return response.text
                    else:
                        raise Exception("Empty response from Gemini API")
                        
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 2 ** retry_count  # Exponential backoff
                        print(f"Error: {e}. Retrying ({retry_count}/{max_retries}) after {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"Max retries reached. Error: {e}")
                        raise
            
            raise Exception("Maximum retries reached without success")
            
        finally:
            # Clean up uploaded file
            if uploaded_file:
                await self._delete_file_async(uploaded_file['name'])
    
    async def _upload_file_async(self, file_path: str, mime_type: str) -> Dict[str, Any]:
        """
        Upload a file to Gemini Files API.
        
        Args:
            file_path: Path to the file
            mime_type: MIME type of the file
            
        Returns:
            Dict with file name and URI
        """
        loop = asyncio.get_event_loop()
        file_obj = await loop.run_in_executor(
            None, 
            lambda: self.client.files.upload(file=file_path)
        )
        
        # Wait a moment for file processing
        await asyncio.sleep(1)
        
        return {
            'name': file_obj.name,
            'uri': file_obj.uri,
            'mime_type': mime_type
        }
    
    async def _delete_file_async(self, file_name: str):
        """
        Delete an uploaded file from Gemini Files API.
        
        Args:
            file_name: Name of the file to delete
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.files.delete(name=file_name)
            )
        except Exception:
            # Silently ignore deletion errors
            pass
    
    def _build_content_parts(
        self, 
        user_prompt: str, 
        text_input: Optional[str], 
        uploaded_file: Optional[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Build content parts for the API request.
        
        Args:
            user_prompt: User's prompt
            text_input: Optional text context
            uploaded_file: Optional uploaded file info
            
        Returns:
            List of content parts
        """
        parts = []
        
        # Add user prompt
        prompt_text = user_prompt
        
        # Add text input if provided
        if text_input:
            prompt_text = f"{user_prompt}\n\nContext:\n{text_input}"
        
        parts.append({"text": prompt_text})
        
        # Add file if uploaded
        if uploaded_file:
            parts.append({
                "file_data": {
                    "mime_type": uploaded_file['mime_type'],
                    "file_uri": uploaded_file['uri']
                }
            })
        
        return parts
    
    def _build_config(
        self,
        response_schema: Optional[BaseModel],
        temperature: float,
        cached_content_name: Optional[str]
    ) -> Dict[str, Any]:
        """
        Build configuration for the API request.
        
        Args:
            response_schema: Optional Pydantic schema for structured output
            temperature: Temperature parameter
            cached_content_name: Optional cache name
            
        Returns:
            Configuration dict
        """
        config = {
            "temperature": temperature
        }
        
        # Add structured output config if schema provided
        if response_schema:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_schema
        
        # Add cache if provided
        if cached_content_name:
            config["cached_content"] = cached_content_name
        
        return config
    
    async def _make_request_async(
        self,
        system_prompt: str,
        content_parts: List[Dict[str, Any]],
        config: Dict[str, Any],
        cached_content_name: Optional[str]
    ):
        """
        Make async request to Gemini API.
        
        Args:
            system_prompt: System prompt
            content_parts: Content parts for the request
            config: Configuration dict
            cached_content_name: Optional cache name
            
        Returns:
            API response
        """
        loop = asyncio.get_event_loop()
        
        # Build contents based on whether we're using cache
        if cached_content_name:
            # With cache, only send user message
            contents = [
                {
                    "role": "user",
                    "parts": content_parts
                }
            ]
        else:
            # Without cache, include system prompt in messages
            contents = [
                {
                    "role": "user",
                    "parts": [{"text": system_prompt}]
                },
                {
                    "role": "model",
                    "parts": [{"text": "Understood. I'm ready to help."}]
                },
                {
                    "role": "user",
                    "parts": content_parts
                }
            ]
        
        # Make request in executor to avoid blocking
        response = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config
            )
        )
        
        return response
    
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
            'webp': 'image/webp'
        }
        return mime_types.get(extension, 'image/jpeg')
