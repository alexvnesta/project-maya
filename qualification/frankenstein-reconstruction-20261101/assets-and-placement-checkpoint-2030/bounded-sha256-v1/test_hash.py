import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fork_hash as f


class Hash(unittest.TestCase):
    def test_whole_SHA_matches_hashlib_across_forked_context_boundaries(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'data';data=bytes(range(256))*4097;p.write_bytes(data)
            row=f.file_sha256(p,hop_bytes=300001)
            self.assertEqual(row['sha256'],hashlib.sha256(data).hexdigest());self.assertEqual(row['bytes'],len(data))
            self.assertEqual(len(row['hops']),4)
            for left,right in zip(row['hops'],row['hops'][1:]):
                self.assertEqual(left['waited_child_pid'],right['observed']['pid']);self.assertEqual(left['waited_child_returncode'],0)
                self.assertEqual(left['end'],right['offset'])
                self.assertEqual(left['observed']['pgid'],right['observed']['pgid'])

    def test_padding_boundary_vectors_and_empty_source(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'data'
            for n in [0,1,55,56,63,64,65,127,128,129]:
                data=b'z'*n;p.write_bytes(data)
                self.assertEqual(f.file_sha256(p,hop_bytes=71)['sha256'],hashlib.sha256(data).hexdigest())

    def test_symlink_hardlink_and_unbounded_hops_rejected(self):
        import os
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();p=root/'data';p.write_bytes(b'data');alias=root/'alias';alias.symlink_to(p)
            with self.assertRaises(ValueError):f.file_sha256(alias)
            alias.unlink();os.link(p,alias)
            with self.assertRaises(ValueError):f.file_sha256(p)
            alias.unlink()
            for size in [0,True,f.MAX_HOP+1]:
                with self.assertRaises(ValueError):f.file_sha256(p,hop_bytes=size)

    def test_unqualified_resources_multithread_or_changed_source_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'data';p.write_bytes(b'data')
            with patch.object(f.threading,'active_count',return_value=2),self.assertRaises(ValueError):f.file_sha256(p)
            row=f.observed();row['cpu']=[60,60]
            with self.assertRaises(ValueError):f.bounds(row)

    def test_forked_child_failure_is_not_accepted_or_retried(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'data';p.write_bytes(b'abcd')
            # A source read short in the second inherited hop must propagate
            # actual child nonzero rather than emit a partial/stand-in digest.
            pread=f.os.pread
            def short(fd,count,offset):return b'' if offset>=2 else pread(fd,count,offset)
            with patch.object(f.os,'pread',side_effect=short),self.assertRaises(ValueError):f.file_sha256(p,hop_bytes=2)


if __name__=='__main__':unittest.main(verbosity=2)
