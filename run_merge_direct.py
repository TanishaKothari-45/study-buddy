#!/usr/bin/env python3
"""
Direct execution of merge_into_pipeline.py for Geography > Oceanography
"""
import sys
import os
from pathlib import Path

# Set up environment
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

# Change to project root for relative imports
os.chdir(project_root)

# Import and run merge script directly
import importlib.util
spec = importlib.util.spec_from_file_location(
    "merge_into_pipeline",
    project_root / "backend" / "scripts" / "merge_into_pipeline.py"
)
merge_module = importlib.util.module_from_spec(spec)

# Simulate command-line arguments
sys.argv = [
    "merge_into_pipeline.py",
    "--subject", "Geography",
    "--domain", "Oceanography",
    "--research-dir", str(project_root / "config" / "research" / "2026-04-03_1700_Geography_Oceanography")
]

# Execute the module
spec.loader.exec_module(merge_module)
merge_module.main()
