#!/usr/bin/env python3
"""Test PaddleOCR initialization"""
import os
# Set environment variables before imports
os.environ['NNPACK_DISABLE'] = '1'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['USE_NNPACK'] = '0'

try:
    import paddle
    print(f"✅ PaddlePaddle version: {paddle.__version__}")
    print(f"✅ Device: {paddle.device.get_device()}")
except ImportError as e:
    print(f"❌ PaddlePaddle not found: {e}")

try:
    from paddleocr import PaddleOCR
    print("\n🔧 Initializing PaddleOCR...")
    ocr = PaddleOCR(use_angle_cls=True, lang='en')
    print("✅ PaddleOCR initialized successfully!")
    print("✅ Ready to use: ocr.ocr(img) for each page")
except Exception as e:
    print(f"❌ PaddleOCR initialization failed: {e}")
    import traceback
    traceback.print_exc()



