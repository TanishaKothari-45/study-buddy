"""
OpenAI client patches to handle legacy arguments and prevent recursion
"""
import openai
from openai import OpenAI

def patch_openai():
    """
    Apply patches to OpenAI client to handle legacy arguments safely
    """
    # Only patch once
    if not getattr(openai, "_global_patches_applied", False):
        # Patch the OpenAI class constructor
        original_init = OpenAI.__init__

        def safe_init(self, *args, **kwargs):
            # Remove problematic arguments
            kwargs.pop("proxies", None)
            kwargs.pop("timeout", None)
            kwargs.pop("organization", None)
            kwargs.pop("max_retries", None)
            # Call original init with cleaned kwargs
            return original_init(self, *args, **kwargs)

        OpenAI.__init__ = safe_init

        # Patch the embeddings.create method
        if hasattr(openai, "Embeddings"):
            original_create = openai.Embeddings.create

            def safe_create(self, *args, **kwargs):
                # Remove problematic arguments
                kwargs.pop("proxies", None)
                kwargs.pop("timeout", None)
                # Call original create with cleaned kwargs
                return original_create(self, *args, **kwargs)

            openai.Embeddings.create = safe_create

        # Mark as patched globally
        openai._global_patches_applied = True
        print("✅ OpenAI client patched to handle legacy arguments safely")
