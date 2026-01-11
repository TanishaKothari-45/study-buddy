"""
Error Handlers Utility
Standardized error cleaning and formatting for AI responses.
"""

import logging

logger = logging.getLogger(__name__)

def clean_gemini_error(error_msg: str) -> str:
    """
    Clean Gemini API error messages for user-friendly display.
    Provides actionable guidance to help users resolve the issue.
    """
    # For quota errors (429)
    if '429' in error_msg and 'quota' in error_msg.lower():
        return "AI Error: You have exceeded your Gemini API quota. Please check your usage at https://aistudio.google.com/app/apikey and upgrade your plan if needed, or try again after some time."
    
    if '429' in error_msg and 'rate limit' in error_msg.lower():
        return "AI Error: Too many requests to Gemini API. Please wait a few minutes and try again."
    
    # For auth errors
    lower_msg = error_msg.lower()
    if 'api_key_invalid' in error_msg or 'api key not valid' in lower_msg or 'invalid api key' in lower_msg:
        return "AI Error: Invalid Gemini API key. Please update your API key in Settings. You can get a new key from https://aistudio.google.com/app/apikey"
    
    # For timeout errors
    if 'timeout' in error_msg.lower() or 'timed out' in error_msg.lower():
        return "AI Error: Request timed out. The AI service is taking longer than expected. Please try again, or try with a shorter question."
    
    # For network/connection errors
    if 'connection' in error_msg.lower() or 'network' in error_msg.lower():
        return "AI Error: Network connection error. Please check your internet connection and try again."
    
    # For empty response
    if 'empty response' in error_msg.lower():
        return "AI Error: Received empty response from AI service. This is usually temporary - please try again in a moment."
    
    # For service unavailable
    if 'service unavailable' in error_msg.lower() or '503' in error_msg:
        return "AI Error: AI service is temporarily unavailable. Please try again in a few minutes."
    
    # For server errors
    if '500' in error_msg or 'internal server error' in error_msg.lower():
        return "AI Error: Server error occurred. We're working to fix this. Please try again or contact support if the issue persists."
    
    # Generic fallback with first sentence
    first_line = error_msg.split('\n')[0]
    first_sentence = first_line.split('.')[0]
    
    # Limit to reasonable length
    if len(first_sentence) > 120:
        first_sentence = first_sentence[:117] + '...'
    
    # Always prefix with "AI Error:"
    if first_sentence and not first_sentence.startswith('AI Error'):
        return f"AI Error: {first_sentence}. Please try again or contact support if the issue persists."
    
    return "AI Error: An unexpected error occurred. Please try again or contact support if the issue persists."
