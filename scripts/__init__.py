"""Command-line scripts; resolve application modules from src/ when invoked with -m."""
from pathlib import Path
import sys

source = str(Path(__file__).resolve().parent.parent / 'src')
if source not in sys.path:
    sys.path.insert(0, source)
