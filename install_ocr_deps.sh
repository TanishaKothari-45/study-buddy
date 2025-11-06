#!/bin/bash

echo "🔧 Installing DeepSeek-OCR dependencies..."

# Install PyTorch (CPU version for compatibility)
echo "📦 Installing PyTorch..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install transformers and other OCR dependencies
echo "📦 Installing transformers and OCR dependencies..."
pip install transformers>=4.30.0
pip install pdf2image
pip install Pillow>=9.0.0
pip install "opencv-python-headless>=4.5.0,<4.9"
pip install addict>=2.4.0
pip install matplotlib>=3.5.0
pip install einops>=0.8.0

# Install poppler-utils for pdf2image (system dependency)
echo "📦 Installing system dependencies..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if command -v brew &> /dev/null; then
        brew install poppler
    else
        echo "⚠️  Please install Homebrew first, then run: brew install poppler"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    sudo apt-get update
    sudo apt-get install -y poppler-utils
else
    echo "⚠️  Please install poppler-utils for your system manually"
fi

echo "✅ DeepSeek-OCR dependencies installed!"
echo "🚀 You can now use handwritten answer evaluation!"
