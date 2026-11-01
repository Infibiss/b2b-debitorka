"""Private creation and permission checks use the host's real access model."""
import os
import subprocess

import pytest

from scripts.private_files import create_private, is_private


def test_private_file_is_exclusive_non_inheritable_and_writable(tmp_path):
    path=tmp_path/'private-file'
    fd=create_private(path)
    assert not os.get_inheritable(fd)
    with os.fdopen(fd,'wb') as handle:
        handle.write(b'private test content')
        handle.flush()
        os.fsync(handle.fileno())
    assert is_private(path)
    assert path.read_bytes()==b'private test content'
    with pytest.raises(FileExistsError):
        create_private(path)
    assert path.read_bytes()==b'private test content'
    if os.name!='nt':
        assert path.stat().st_mode&0o777==0o600


def test_public_file_and_missing_path_are_not_private(tmp_path):
    assert not is_private(tmp_path/'missing')
    path=tmp_path/'public-file'
    path.write_bytes(b'public test content')
    if os.name!='nt':
        path.chmod(0o644)
    else:
        # Make the distinction independent of the parent test directory's ACL.
        result=subprocess.run(['icacls',str(path),'/grant','*S-1-1-0:R'],capture_output=True)
        assert result.returncode==0
    assert not is_private(path)
