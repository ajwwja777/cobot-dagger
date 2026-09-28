#!/usr/bin/env python3
"""Read-only dataset/label summary; no ROS connection and no writes."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from capture_core.labels import LabelStore
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args=parser.parse_args()
    rows=LabelStore(args.directory).list_episodes()
    outcomes={}
    for row in rows:
        key=row.get("outcome",row.get("episode_outcome","unknown"))
        outcomes[key]=outcomes.get(key,0)+1
    print(json.dumps({"directory":str(args.directory.resolve()),"episodes":len(rows),"outcomes":outcomes},indent=2))
if __name__=="__main__":main()
