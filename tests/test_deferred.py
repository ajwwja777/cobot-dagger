import hashlib
from pathlib import Path
from uuid import uuid4
import h5py
import pytest
from capture_core.deferred import metadata, defer_file, list_deferred, delete_deferred
from capture_core.storage import prepare_series, SeriesIdentity

def test_deferred_and_deleted_receipt_keep_index_reserved(tmp_path):
    path=tmp_path/'episode_000007.hdf5.incomplete';uuid=str(uuid4())
    with h5py.File(path,'w') as f:f.attrs['episode_uuid']=uuid;f.attrs['completion_state']='incomplete'
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    row=defer_file(tmp_path,metadata(path))
    assert hashlib.sha256((tmp_path/row['archive_relative_path']).read_bytes()).hexdigest()==before
    series=SeriesIdentity('task','model','round',storage_layout='flat')
    assert prepare_series(tmp_path,series).next_episode_index==8
    delete_deferred(tmp_path,uuid)
    assert prepare_series(tmp_path,series).next_episode_index==8 and list_deferred(tmp_path)==[]

def test_symlink_and_modified_archive_refused(tmp_path):
    path=tmp_path/'episode_000001.hdf5';path.write_bytes(b'invalid retained bytes')
    link=tmp_path/'episode_000002.hdf5';link.symlink_to(path)
    with pytest.raises(ValueError,match='symlink'):defer_file(tmp_path,metadata(link))
    row=defer_file(tmp_path,metadata(path));archive=tmp_path/row['archive_relative_path']
    archive.write_bytes(b'altered retained bytes')
    with pytest.raises(ValueError,match='changed'):delete_deferred(tmp_path,row['episode_uuid'])
    assert archive.exists()
