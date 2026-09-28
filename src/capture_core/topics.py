"""Shared ROS names are owned by cobot-control."""
import os
import sys
from pathlib import Path
_root = Path(os.environ.get("COBOT_CONTROL_PROJECT_ROOT",
    Path(__file__).resolve().parents[3] / "cobot-control"))
sys.path.insert(0, str(_root / "src"))
from cobot_control.ros_topics import *
