#!/bin/bash
cd /Users/tanishakothari/Documents/Personal/study-buddy
source venv/bin/activate
python3 backend/scripts/merge_into_pipeline.py \
  --subject "Geography" \
  --domain "Oceanography" \
  --research-dir "/Users/tanishakothari/Documents/Personal/study-buddy/config/research/2026-04-03_1700_Geography_Oceanography/"
