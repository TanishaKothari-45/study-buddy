"""
ROI (Region of Interest) detection for answer sheets
Uses Hough Lines to detect answer box boundaries with fallback to percentage-based cropping
"""
import cv2
import numpy as np
import logging
from typing import Tuple, Optional
from PIL import Image

logger = logging.getLogger(__name__)

def preprocess_for_ocr(img: np.ndarray, enhance_contrast: bool = True, 
                       denoise: bool = True, deskew: bool = True,
                       remove_noise: bool = True) -> np.ndarray:
    """
    Enhanced preprocessing for OCR: grayscale, denoise, contrast enhancement, 
    morphological operations, deskewing, and adaptive threshold
    
    Args:
        img: Input image (BGR format from OpenCV)
        enhance_contrast: Apply CLAHE contrast enhancement
        denoise: Apply bilateral filter for noise removal
        deskew: Correct image rotation/skew
        remove_noise: Apply morphological operations to remove small noise
    
    Returns:
        Preprocessed binary image ready for OCR
    """
    logger.info("🔧 Starting image preprocessing...")
    
    # Step 1: Convert to grayscale
    logger.debug("   Step 1/7: Converting to grayscale")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    logger.debug(f"      • Image shape: {gray.shape}")
    
    # Step 2: Initial denoising with median filter (removes salt-and-pepper noise)
    logger.debug("   Step 2/7: Applying median blur (salt-and-pepper noise removal)")
    den = cv2.medianBlur(gray, 3)
    
    # Step 3: Bilateral filter (better denoising while preserving edges)
    if denoise:
        logger.debug("   Step 3/7: Applying bilateral filter (edge-preserving denoise)")
        den = cv2.bilateralFilter(den, 9, 75, 75)
        logger.debug("      • Bilateral filter applied (d=9, sigmaColor=75, sigmaSpace=75)")
    
    # Step 4: Contrast enhancement with CLAHE
    if enhance_contrast:
        logger.debug("   Step 4/7: Applying CLAHE (Contrast Limited Adaptive Histogram Equalization)")
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        den = clahe.apply(den)
        logger.debug("      • CLAHE applied (clipLimit=2.0, tileGridSize=8x8)")
    
    # Step 5: Deskewing (rotation correction)
    if deskew:
        logger.debug("   Step 5/7: Detecting and correcting skew/rotation")
        try:
            # Detect skew angle
            coords = np.column_stack(np.where(den > 0))
            if len(coords) > 0:
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle
                
                # Only correct if angle is significant (> 0.5 degree)
                if abs(angle) > 0.5:
                    (h, w) = den.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    den = cv2.warpAffine(den, M, (w, h), 
                                         flags=cv2.INTER_CUBIC, 
                                         borderMode=cv2.BORDER_REPLICATE)
                    logger.debug(f"      • Deskewed by {angle:.2f} degrees")
                else:
                    logger.debug(f"      • Skew angle ({angle:.2f}°) too small, skipping correction")
        except Exception as e:
            logger.warning(f"      ⚠️ Deskewing failed: {e}. Continuing without deskewing.")
    
    # Step 6: Morphological operations to remove small noise (dots, lines)
    if remove_noise:
        logger.debug("   Step 6/7: Applying morphological operations (noise removal)")
        # Remove small dots and noise
        kernel = np.ones((2, 2), np.uint8)
        den = cv2.morphologyEx(den, cv2.MORPH_CLOSE, kernel)
        # Remove thin lines and artifacts
        kernel_line = np.ones((1, 3), np.uint8)
        den = cv2.morphologyEx(den, cv2.MORPH_OPEN, kernel_line)
        logger.debug("      • Morphological operations applied (close + open)")
    
    # Step 7: Adaptive threshold (convert to binary)
    logger.debug("   Step 7/7: Applying adaptive threshold (binary conversion)")
    thr = cv2.adaptiveThreshold(den, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 11, 2)
    logger.info("✅ Image preprocessing completed")
    
    return thr

def fallback_percent_crop(img: np.ndarray) -> np.ndarray:
    """
    Fallback ROI extraction using percentage-based cropping
    Tweaked for standard answer sheet format
    
    Args:
        img: Input image
    
    Returns:
        Cropped ROI image
    """
    h, w = img.shape[:2]
    # Further reduced top and bottom margins to include more content
    # Top crop: reduced to 5% (was 10%)
    # Bottom crop: reduced to 2% (was 3%)
    top = int(h * 0.05)  # Reduced from 0.10 (10%) to 0.05 (5%)
    bottom = int(h * 0.98)  # Reduced from 0.97 (3% bottom crop) to 0.98 (2% bottom crop)
    left = int(w * 0.09)
    right = int(w * 0.91)
    return img[top:bottom, left:right]

def detect_roi_lines(img: np.ndarray) -> Tuple[int, int, int, int]:
    """
    Detect ROI boundaries using Hough Lines
    Detects both top and bottom horizontal lines to crop everything outside the answer box
    
    Args:
        img: Input image (BGR format)
    
    Returns:
        Tuple of (top, bottom, left, right) coordinates
    
    Raises:
        Exception: If lines cannot be detected
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=200,
                            minLineLength=300, maxLineGap=20)
    
    if lines is None:
        raise Exception("No lines detected")
    
    verticals = []
    horizontals = []
    
    for x1, y1, x2, y2 in lines[:, 0]:
        if abs(x1 - x2) < 20:   # vertical
            verticals.append((x1, y1, x2, y2))
        if abs(y1 - y2) < 20:   # horizontal
            horizontals.append((x1, y1, x2, y2))
    
    if len(verticals) < 2 or len(horizontals) < 1:
        raise Exception("not enough borders")
    
    # Pick left-most & right-most verticals
    xs = sorted(verticals, key=lambda p: p[0])
    left_line = xs[0][0]
    right_line = xs[-1][0]
    
    # Pick top-most and bottom-most horizontal lines
    ys = sorted(horizontals, key=lambda p: p[1])
    top_line = ys[0][1]
    bottom_line = ys[-1][1]
    
    # Small inner margin (avoid border thickness)
    margin = 10
    
    # Ensure we don't crop more than 12% from bottom
    # Many UPSC answers have last 2-3 lines very close to bottom border
    h = img.shape[0]
    detected_bottom = bottom_line - margin
    max_allowed_bottom = int(h * 0.90)  # Keep at least 90% of height (crop max 10%)
    
    # Use the higher value (closer to original bottom) to preserve more content
    final_bottom = max(detected_bottom, max_allowed_bottom)
    
    # Also ensure we don't crop more than 5% from top
    detected_top = top_line + margin
    min_allowed_top = int(h * 0.05)  # Crop max 5% from top
    final_top = min(detected_top, min_allowed_top) if detected_top < min_allowed_top else detected_top
    
    logger.info(f"   📐 Hough Lines detection:")
    logger.info(f"      • Detected top: {detected_top}, final top: {final_top} (crop {final_top/h*100:.1f}% from top)")
    logger.info(f"      • Detected bottom: {detected_bottom}, final bottom: {final_bottom} (keep {(final_bottom-final_top)/h*100:.1f}% of height)")
    
    return final_top, final_bottom, left_line + margin, right_line - margin

def extract_answer_roi(img: np.ndarray, use_fallback: bool = False) -> Tuple[np.ndarray, dict]:
    """
    Extract answer ROI from image (returns clean RGB crop, NO preprocessing)
    
    ROI detection needs clean original image for edge detection and Hough Lines.
    Preprocessing happens AFTER ROI extraction.
    
    Args:
        img: Input image (BGR format from OpenCV)
        use_fallback: Force use of fallback method
    
    Returns:
        Tuple of (RGB ROI image, metadata dict with detection info)
    """
    metadata = {
        "method": "unknown",
        "coordinates": None,
        "success": False
    }
    
    try:
        if use_fallback:
            raise Exception("Forcing fallback")
        
        top, bottom, left, right = detect_roi_lines(img)
        
        # Crop using detected top, bottom, left, right boundaries (BGR format)
        roi_bgr = img[top:bottom, left:right]
        
        # Convert BGR to RGB for return (no preprocessing here!)
        roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
        
        metadata = {
            "method": "hough_lines",
            "coordinates": {
                "top": int(top),
                "left": int(left),
                "right": int(right),
                "bottom": int(bottom)
            },
            "success": True
        }
        
        logger.info(f"✅ ROI detected using Hough Lines: top={top}, bottom={bottom}, left={left}, right={right}")
        logger.info(f"   📐 ROI crop size: {roi_rgb.shape[1]}x{roi_rgb.shape[0]} pixels (RGB)")
        return roi_rgb, metadata
        
    except Exception as e:
        # Fallback to percentage-based cropping
        logger.warning(f"⚠️ Hough Lines detection failed: {e}. Using fallback percentage crop.")
        
        roi_bgr = fallback_percent_crop(img)
        
        # Convert BGR to RGB (no preprocessing)
        roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
        
        h, w = img.shape[:2]
        # Crop only 5% from top, 10% from bottom (keep 90% of height)
        # This ensures last 2-3 lines near bottom border are preserved
        top = int(h * 0.06)  # 8% crop from top
        bottom = int(h * 0.93)  # 10% crop from bottom (keep 90% of height)
        left = int(w * 0.09)  # 9% crop from left
        right = int(w * 0.91)  # 9% crop from right
        logger.info(f"   📐 Fallback crop: keeping {bottom-top}/{h} pixels height ({((bottom-top)/h)*100:.1f}%)")
        
        metadata = {
            "method": "fallback_percent",
            "coordinates": {
                "top": top,
                "left": left,
                "right": right,
                "bottom": bottom
            },
            "success": True
        }
        
        logger.info(f"✅ ROI extracted using fallback: top={top}, left={left}, right={right}, bottom={bottom}")
        logger.info(f"   📐 ROI crop size: {roi_rgb.shape[1]}x{roi_rgb.shape[0]} pixels (RGB)")
        return roi_rgb, metadata

def detect_roi_from_sample(sample_image_path: str) -> Optional[dict]:
    """
    Detect ROI from a sample sheet and return coordinates for reuse
    
    Args:
        sample_image_path: Path to sample sheet image
    
    Returns:
        Dictionary with ROI coordinates, or None if detection fails
    """
    try:
        # Load sample image
        img = cv2.imread(sample_image_path)
        if img is None:
            logger.error(f"Failed to load sample image: {sample_image_path}")
            return None
        
        # Try to detect ROI (returns RGB crop, but we only need coordinates)
        _, metadata = extract_answer_roi(img, use_fallback=False)
        
        if metadata["success"]:
            logger.info(f"✅ ROI detected from sample sheet: {metadata['coordinates']}")
            return metadata["coordinates"]
        else:
            # Try fallback
            _, metadata = extract_answer_roi(img, use_fallback=True)
            if metadata["success"]:
                logger.info(f"✅ ROI detected from sample sheet (fallback): {metadata['coordinates']}")
                return metadata["coordinates"]
            
    except Exception as e:
        logger.error(f"❌ Failed to detect ROI from sample sheet: {e}")
    
    return None

def apply_roi_to_image(img: np.ndarray, roi_coords: dict) -> np.ndarray:
    """
    Apply pre-detected ROI coordinates to an image (returns clean RGB crop, NO preprocessing)
    
    Preprocessing happens AFTER ROI extraction.
    
    Args:
        img: Input image (BGR format)
        roi_coords: Dictionary with top, left, right, bottom coordinates
    
    Returns:
        RGB ROI image (no preprocessing applied)
    """
    top = roi_coords["top"]
    left = roi_coords["left"]
    right = roi_coords["right"]
    bottom = roi_coords["bottom"]
    
    # Crop ROI (BGR format)
    roi_bgr = img[top:bottom, left:right]
    
    # Convert BGR to RGB (no preprocessing!)
    roi_rgb = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB)
    
    return roi_rgb

