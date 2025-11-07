"""
Image preprocessing utilities for handwritten answer OCR
"""
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class HandwrittenImagePreprocessor:
    def __init__(self):
        """Initialize image preprocessor for handwritten text"""
        self.target_size = (1024, 1024)  # DeepSeek-OCR optimal size
        
    def preprocess_image(self, image: Image.Image) -> dict:
        """
        Comprehensive preprocessing pipeline for handwritten images
        Returns both processed image and preprocessing steps info
        """
        try:
            # Convert PIL to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            original_shape = cv_image.shape
            
            # Step 1: Resize while maintaining aspect ratio
            resized = self._resize_image(cv_image)
            
            # Step 2: Convert to grayscale
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            
            # Step 3: Noise reduction
            denoised = self._denoise_image(gray)
            
            # Step 4: Deskew correction
            deskewed = self._deskew_image(denoised)
            
            # Step 5: Contrast enhancement
            enhanced = self._enhance_contrast(deskewed)
            
            # Step 6: Adaptive thresholding
            thresholded = self._adaptive_threshold(enhanced)
            
            # Step 7: Morphological operations
            cleaned = self._morphological_cleanup(thresholded)
            
            # Step 8: Final resize to target size
            final = self._final_resize(cleaned)
            
            # Convert back to PIL
            processed_pil = Image.fromarray(final)
            
            return {
                "processed_image": processed_pil,
                "preprocessing_steps": {
                    "original_size": original_shape[:2],
                    "resized_size": resized.shape[:2],
                    "final_size": final.shape,
                    "skew_angle": self._get_skew_angle(denoised),
                    "contrast_factor": 1.5,
                    "threshold_method": "adaptive"
                },
                "success": True
            }
            
        except Exception as e:
            logger.error(f"❌ Image preprocessing failed: {e}")
            return {
                "processed_image": image,  # Return original if preprocessing fails
                "preprocessing_steps": {"error": str(e)},
                "success": False
            }
    
    def _resize_image(self, image: np.ndarray) -> np.ndarray:
        """Resize image while maintaining aspect ratio"""
        h, w = image.shape[:2]
        max_dim = max(h, w)
        
        # Resize so the larger dimension is 1200px
        if max_dim > 1200:
            scale = 1200 / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return image
    
    def _denoise_image(self, image: np.ndarray) -> np.ndarray:
        """Remove noise from grayscale image"""
        # Bilateral filter for noise reduction while preserving edges
        return cv2.bilateralFilter(image, 9, 75, 75)
    
    def _deskew_image(self, image: np.ndarray) -> np.ndarray:
        """Correct skew in handwritten text"""
        # Find contours
        contours, _ = cv2.findContours(image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return image
        
        # Get the largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Get minimum area rectangle
        rect = cv2.minAreaRect(largest_contour)
        angle = rect[2]
        
        # Correct angle if it's too steep
        if angle < -45:
            angle += 90
        elif angle > 45:
            angle -= 90
        
        # Only rotate if angle is significant
        if abs(angle) > 0.5:
            h, w = image.shape
            center = (w // 2, h // 2)
            rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
            return cv2.warpAffine(image, rotation_matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        
        return image
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """Enhance contrast for better text visibility"""
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)
    
    def _adaptive_threshold(self, image: np.ndarray) -> np.ndarray:
        """Apply adaptive thresholding for better text extraction"""
        # Use adaptive threshold to handle varying lighting
        return cv2.adaptiveThreshold(
            image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
    
    def _morphological_cleanup(self, image: np.ndarray) -> np.ndarray:
        """Clean up image using morphological operations"""
        # Remove small noise
        kernel = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)
        
        # Fill small holes
        kernel = np.ones((3, 3), np.uint8)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
        
        return cleaned
    
    def _final_resize(self, image: np.ndarray) -> np.ndarray:
        """Resize to target size for DeepSeek-OCR"""
        return cv2.resize(image, self.target_size, interpolation=cv2.INTER_CUBIC)
    
    def _get_skew_angle(self, image: np.ndarray) -> float:
        """Calculate skew angle for reporting"""
        try:
            # Use HoughLines to detect text lines
            edges = cv2.Canny(image, 50, 150, apertureSize=3)
            lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
            
            if lines is not None:
                angles = []
                for line in lines:
                    rho, theta = line[0]
                    angle = theta * 180 / np.pi
                    if 45 < angle < 135:  # Horizontal lines
                        angles.append(angle - 90)
                
                if angles:
                    return np.median(angles)
            
            return 0.0
        except:
            return 0.0

# Global instance
_preprocessor = None

def get_image_preprocessor() -> HandwrittenImagePreprocessor:
    """Get or create image preprocessor instance"""
    global _preprocessor
    if _preprocessor is None:
        try:
            import cv2
            _preprocessor = HandwrittenImagePreprocessor()
        except ImportError:
            logger.warning("⚠️ OpenCV not available. Install with: pip install opencv-python")
            return None
    return _preprocessor


