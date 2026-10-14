"""Operator results for committed, autonomous episodes with only node images."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4


def read_node_episode(sidecar, episode_uuid):
    """Validate a committed node-only sidecar without modifying it."""
    sidecar = Path(sidecar)
    identity = str(UUID(str(episode_uuid)))
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
    return payload


def write_node_outcome(sidecar, episode_uuid, outcome):
    """Persist a result without inventing a complete HDF5 or HIL training frames."""
    if outcome not in {"success", "failure", "unknown"}:
        raise ValueError("invalid_outcome")
    sidecar = Path(sidecar)
    payload = read_node_episode(sidecar, episode_uuid)
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


def inspect_closed_node_file(path, data_root):
    """Recognize only a closed empty HDF5 paired with a validated node result.

    The HDF5 remains incomplete and unusable for training. Its associated
    segmented episode is complete, so it need not block the next recording.
    """
    import h5py
    path, root = Path(path), Path(data_root).resolve()
    try:
        if path.is_symlink() or path.resolve() != path:
            return None
        relative = path.relative_to(root).as_posix()
        if not relative.endswith('.hdf5.incomplete'):
            return None
        with h5py.File(path, 'r') as handle:
            identity = str(UUID(str(handle.attrs['episode_uuid'])))
            if handle.attrs.get('completion_state') != 'error' or handle.attrs.get('failure_reason') != 'empty_episode':
                return None
            # An empty writer has no frame datasets, including partial datasets.
            datasets = []
            handle.visititems(lambda name, item: datasets.append(name) if isinstance(item, h5py.Dataset) else None)
            if datasets:
                return None
            index = int(handle.attrs['episode_index'])
            if path.name != f'episode_{index:06d}.hdf5.incomplete':
                return None
            fields = {key: str(handle.attrs[key]) for key in ('task_id', 'model_id', 'dataset_round')}
        candidates = [root / '.segments' / identity,
                      root / '.segments' / fields['task_id'] / fields['model_id'] / fields['dataset_round'] / identity]
        candidates = [folder for folder in candidates if (folder / 'sidecar.json').is_file()]
        if len(candidates) != 1:
            return None
        folder = candidates[0]
        if folder.resolve() != folder or root not in folder.resolve().parents:
            return None
        payload = read_node_episode(folder / 'sidecar.json', identity)
        if (payload.get('source_hdf5_relative') != relative[:-len('.incomplete')]
                or payload.get('episode_index') != index
                or any(payload.get(key) != value for key, value in fields.items())
                or payload.get('outcome_storage') != 'segmented_sidecar'
                or payload.get('episode_outcome') not in {'success', 'failure', 'unknown'}):
            return None
        return payload
    except (OSError, ValueError, KeyError, TypeError):
        return None
