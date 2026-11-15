#!/usr/bin/env python3
"""Create separate H.264 MP4 copies; never alter source AVI or video.json."""
import argparse
from capture_core.browser_video import convert_archive
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("archives",nargs="+",help="Finalized legacy archive directories")
if __name__=="__main__":
    args=parser.parse_args()
    for directory in args.archives:convert_archive(directory)
