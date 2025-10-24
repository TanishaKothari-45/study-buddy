#!/bin/bash

echo "🚀 Setting up Study Buddy dependencies..."

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt

# Install system dependencies for PDF conversion
echo "🔧 Installing system dependencies..."

# For pdfkit (wkhtmltopdf)
if command -v apt-get &> /dev/null; then
    # Ubuntu/Debian
    sudo apt-get update
    sudo apt-get install -y wkhtmltopdf
elif command -v yum &> /dev/null; then
    # CentOS/RHEL
    sudo yum install -y wkhtmltopdf
elif command -v brew &> /dev/null; then
    # macOS
    brew install wkhtmltopdf
else
    echo "⚠️  Could not install wkhtmltopdf automatically."
    echo "   Please install manually:"
    echo "   - Ubuntu/Debian: sudo apt-get install wkhtmltopdf"
    echo "   - macOS: brew install wkhtmltopdf"
    echo "   - Windows: Download from https://wkhtmltopdf.org/downloads.html"
fi

# For weasyprint (alternative PDF converter)
echo "📄 Installing weasyprint dependencies..."
pip install weasyprint

echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Set your OPENAI_API_KEY: export OPENAI_API_KEY='your-key-here'"
echo "2. Start backend: cd backend && python main.py"
echo "3. Start frontend: cd frontend && streamlit run app.py"
echo "4. Test acquisition: python test_acquisition.py"
