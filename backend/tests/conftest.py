"""Pytest configuration for backend tests.

Ensures the repository root is on ``sys.path`` so test collection can
import the ``backend`` package reliably regardless of the working
directory used to invoke pytest.
"""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
