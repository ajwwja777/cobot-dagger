"""Operator results for committed, autonomous episodes with only node images."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


def write_node_outcome(sidecar, episode_uuid, outcome):
    """Persist a result without inventing a complete HDF5 or HIL training frames."""
    sidecar = Path(sidecar)
    identity = str(UUID(str(episode_uuid)))
    if outcome not in {"success", "failure", "unknown"}:
        raise ValueError("invalid_outcome")
    if sidecar.name != "sidecar.json" or sidecar.parent.name != identity or sidecar.is_symlink():
        raise ValueError("invalid_node_sidecar")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    nodes = payload.get("nodes", [])
    if (payload.get("episode_uuid") != identity
            or payload.get("commit_state") != "complete"
            or payload.get("capture_state") != "committed"
            or type(payload.get("training_frame_count")) is not int
            or payload["training_frame_count"] != 0
            or payload.get("training_intervals") != []
            or payload.get("active_segments") != []
            or not nodes or nodes[0].get("kind") != "start" or nodes[-1].get("kind") != "end"
            or any(node.get("teach_mask") != {"left": False, "right": False} for node in nodes)):
        raise ValueError("not_finalized_node_only_episode")
    if payload.get("episode_outcome") == outcome:
        return payload
    payload.update(episode_outcome=outcome, has_hil=False, outcome_storage="segmented_sidecar",
                   label_updated_at=datetime.now(timezone.utc).isoformat())
    temporary = sidecar.with_name(".outcome-" + str(uuid4()) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, sidecar)
        directory = os.open(str(sidecar.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return payload
