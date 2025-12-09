#!/bin/bash
# Helper script to run add_intrinsic_scores.py with virtual environment activated

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Activate virtual environment
if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "🔧 Activating virtual environment from $SCRIPT_DIR/venv..."
    source "$SCRIPT_DIR/venv/bin/activate"
elif [ -d "$SCRIPT_DIR/../venv" ]; then
    echo "🔧 Activating virtual environment from $SCRIPT_DIR/../venv..."
    source "$SCRIPT_DIR/../venv/bin/activate"
else
    echo "⚠️  Warning: Virtual environment not found. Make sure venv is set up."
    echo "   Looking for: $SCRIPT_DIR/venv or $SCRIPT_DIR/../venv"
    exit 1
fi

# Check if activation was successful
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ Failed to activate virtual environment"
    exit 1
fi

echo "✅ Virtual environment activated: $VIRTUAL_ENV"
echo ""

# Change to backend directory
cd "$SCRIPT_DIR/backend" || {
    echo "❌ Failed to change to backend directory"
    exit 1
}

# Run the script with all passed arguments (now in backend/scripts/)
echo "🚀 Running add_intrinsic_scores.py..."
echo ""
python3 scripts/add_intrinsic_scores.py "$@"

# Capture exit code
EXIT_CODE=$?

# Deactivate virtual environment
deactivate 2>/dev/null || true

exit $EXIT_CODE


