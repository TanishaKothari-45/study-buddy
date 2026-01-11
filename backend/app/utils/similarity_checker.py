"""
Similarity checker for determining if questions are on the same topic.
Uses sentence embeddings to calculate semantic similarity.
"""
import numpy as np
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)


class SimilarityChecker:
    """
    Semantic similarity checker using sentence embeddings.
    
    Uses a lightweight model (all-MiniLM-L6-v2) for fast similarity calculations.
    """
    
    # Similarity thresholds
    HIGH_SIMILARITY = 0.75   # Definitely same topic - use cached docs
    MEDIUM_SIMILARITY = 0.50  # Related topic - retrieve fresh + keep previous context
    
    def __init__(self):
        """Initialize the similarity checker with the embedding model."""
        logger.info("🔧 Loading sentence embedding model (all-MiniLM-L6-v2)...")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("✅ Embedding model loaded successfully")
    
    def encode(self, text: str) -> np.ndarray:
        """
        Encode text into embedding vector.
        
        Args:
            text: Text to encode
            
        Returns:
            Embedding vector as numpy array
        """
        return self.model.encode(text, convert_to_numpy=True)
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate cosine similarity between two texts.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score between 0 and 1
        """
        emb1 = self.encode(text1)
        emb2 = self.encode(text2)
        
        # Cosine similarity
        similarity = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
        
        return float(similarity)
    
    def should_retrieve_new_docs(self, current_question: str, previous_question: str = None) -> tuple[bool, str]:
        """
        Determine if new document retrieval is needed based on question similarity.
        
        Args:
            current_question: The current question being asked
            previous_question: The previous question in the session (if any)
            
        Returns:
            Tuple of (should_retrieve, reason)
            - should_retrieve: True if new docs needed, False if can use cached
            - reason: Explanation of the decision
        """
        if not previous_question:
            return True, "first_question"
        
        similarity = self.calculate_similarity(current_question, previous_question)
        
        if similarity >= self.HIGH_SIMILARITY:
            return False, f"high_similarity_{similarity:.2f}"
        elif similarity >= self.MEDIUM_SIMILARITY:
            return True, f"medium_similarity_{similarity:.2f}"
        else:
            return True, f"low_similarity_{similarity:.2f}"
