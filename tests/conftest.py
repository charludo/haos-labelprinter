import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "custom_components", "brother_ptouch"))
sys.path.insert(0, os.path.join(ROOT, "bridge"))
