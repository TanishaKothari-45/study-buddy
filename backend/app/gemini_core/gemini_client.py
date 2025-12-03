import asyncio
import time
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import google.generativeai as genai


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
        genai.configure(api_key=api_key)
    
    async def generate_response(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        text_input: Optional[str] = None,
        image_path: Optional[str | List[str]] = None,
        pdf_path: Optional[str | List[str]] = None,
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
            image_path: Optional path to image file (or list of image files)
            pdf_path: Optional path to PDF file (or list of PDF files)
            response_schema: Optional Pydantic model for structured output
            temperature: Temperature for response generation (default: 0.0)
            cached_content_name: Optional cache name to use for context caching
            max_retries: Maximum number of retry attempts (default: 2)
            
        Returns:
            Response text (JSON string if response_schema provided, otherwise plain text)
        """
        uploaded_files = []
        retry_count = 0
        
        try:
            # Use default system prompt if none provided
            if system_prompt is None:
                system_prompt = self.DEFAULT_SYSTEM_PROMPT
            
            # Upload files if needed (PDF or images)
            if pdf_path:
                pdf_paths = [pdf_path] if isinstance(pdf_path, str) else pdf_path
                for path in pdf_paths:
                    uploaded_file = await self._upload_file_async(path, "application/pdf")
                    uploaded_files.append(uploaded_file)
            elif image_path:
                image_paths = [image_path] if isinstance(image_path, str) else image_path
                for path in image_paths:
                    mime_type = self._get_image_mime_type(path)
                    uploaded_file = await self._upload_file_async(path, mime_type)
                    uploaded_files.append(uploaded_file)
            
            # Prepare contents
            contents = []
            
            # Add text parts
            prompt_text = user_prompt
            if text_input:
                prompt_text = f"{user_prompt}\n\nContext:\n{text_input}"
            
            parts = [prompt_text]
            
            # Add file parts
            for uploaded_file in uploaded_files:
                parts.append(uploaded_file['file_obj'])
            
            contents.append({"role": "user", "parts": parts})
            
            # Configure generation config
            generation_config = {
                "temperature": temperature
            }
            
            if response_schema:
                generation_config["response_mime_type"] = "application/json"
                generation_config["response_schema"] = response_schema
            
            # Initialize model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt
            )
            
            # Make request with retry logic
            while retry_count < max_retries:
                try:
                    # Run in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: model.generate_content(
                            contents,
                            generation_config=generation_config
                        )
                    )
                    
                    if response and response.text:
                        return response.text
                    else:
                        raise Exception("Empty response from Gemini API")
                        
                except Exception as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 2 ** retry_count
                        print(f"Error: {e}. Retrying ({retry_count}/{max_retries}) after {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"Max retries reached. Error: {e}")
                        raise
            
            raise Exception("Maximum retries reached without success")
            
        finally:
            # Clean up uploaded files
            if uploaded_files:
                for file in uploaded_files:
                    await self._delete_file_async(file['name'])
    
    def create_chat_session(self, system_instruction: str):
        """
        Create a new chat session with system instruction.
        
        Args:
            system_instruction: System-level instructions for the chat
            
        Returns:
            Chat session object
        """
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_instruction
        )
        return model.start_chat(history=[])
    
    def send_chat_message(self, chat, message: str) -> str:
        """
        Send a message to an existing chat session.
        
        Args:
            chat: Chat session object from create_chat_session()
            message: Message to send
            
        Returns:
            Response text from the model
        """
        response = chat.send_message(message)
        return response.text
    
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
            lambda: genai.upload_file(path=file_path, mime_type=mime_type)
        )
        
        # Wait for processing
        while file_obj.state.name == "PROCESSING":
            await asyncio.sleep(1)
            file_obj = await loop.run_in_executor(
                None,
                lambda: genai.get_file(file_obj.name)
            )
            
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
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: genai.delete_file(file_name)
            )
        except Exception:
            pass
            
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
