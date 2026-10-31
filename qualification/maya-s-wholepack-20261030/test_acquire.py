"""Independent synthetic HTTP acquisition controls; no remote connection or weights."""
import hashlib
import io
import pathlib
import tempfile
import unittest
from unittest import mock
import json
import contextlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import acquire as a


class Response(io.BytesIO):
    def __init__(self, body, status=206, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {'Content-Length': str(len(body)),
                                  'Content-Range': 'bytes 0-%d/%d' % (len(body)-1, len(body))}


class Acquisition(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()  # only this test-owned temporary root
        self.data = b'canonical-model-bytes'
        self.spec = {'path': 'Maya-S/test.gguf', 'size': len(self.data),
                     'sha256': hashlib.sha256(self.data).hexdigest()}
        self.calls = []

    def run_file(self, **kw):
        def open_(request, timeout):
            self.calls.append((request.full_url, request.headers, timeout))
            return Response(self.data)
        return a.acquire_file(self.spec, self.root, kw.pop('guard', lambda: None),
                              opener=kw.pop('opener', open_), free=kw.pop('free', lambda: a.RESERVE+10000000),
                              sleeper=lambda _: None, **kw)

    def test_complete_hash_and_atomic_publish(self):
        r = self.run_file()
        self.assertEqual(r['status'], 'DOWNLOADED_VERIFIED')
        self.assertEqual((self.root/self.spec['path']).read_bytes(), self.data)
        self.assertFalse((self.root/(self.spec['path']+'.partial')).exists())

    def test_pinned_transport_and_range(self):
        self.run_file(); u, h, t = self.calls[0]
        self.assertIn('/'+a.REVISION+'/Maya-S/test.gguf', u)
        self.assertEqual(h['Range'], 'bytes=0-%d' % (len(self.data)-1)); self.assertEqual(t, 5)

    def test_resume_hashes_prefix_and_checks_range(self):
        (self.root/'Maya-S').mkdir(); (self.root/'Maya-S/test.gguf.partial').write_bytes(self.data[:5])
        def op(request, timeout):
            self.assertEqual(request.headers['Range'], 'bytes=5-%d' % (len(self.data)-1))
            return Response(self.data[5:], headers={'Content-Length': str(len(self.data)-5),
                'Content-Range': 'bytes 5-%d/%d' % (len(self.data)-1, len(self.data))})
        self.run_file(opener=op)

    def test_corrupt_prefix_never_promoted(self):
        (self.root/'Maya-S').mkdir(); p=self.root/'Maya-S/test.gguf.partial'; p.write_bytes(b'X'*len(self.data))
        with self.assertRaisesRegex(ValueError, 'checksum'): self.run_file()
        self.assertTrue(p.exists()); self.assertFalse((self.root/self.spec['path']).exists())

    def test_checksum_failure_preserves_full_partial(self):
        self.spec['sha256']='0'*64
        with self.assertRaisesRegex(ValueError, 'checksum'): self.run_file()
        self.assertEqual((self.root/'Maya-S/test.gguf.partial').read_bytes(), self.data)

    def test_existing_final_is_verified_without_network(self):
        (self.root/'Maya-S').mkdir(); (self.root/self.spec['path']).write_bytes(self.data)
        self.assertEqual(self.run_file()['status'], 'VERIFIED_EXISTING'); self.assertEqual(self.calls, [])

    def test_corrupt_existing_final_refused(self):
        (self.root/'Maya-S').mkdir(); (self.root/self.spec['path']).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'corrupt'): self.run_file()

    def test_busy_before_directory_or_transport(self):
        def guard(): raise a.Deferred('busy')
        with self.assertRaises(a.Deferred): self.run_file(guard=guard)
        self.assertEqual(list(self.root.iterdir()), []); self.assertEqual(self.calls, [])

    def test_busy_midstream_closes_response_retains_partial(self):
        response = Response(self.data); calls = [0]
        def guard():
            calls[0] += 1
            if calls[0] == 4: raise a.Deferred('busy')
        with self.assertRaises(a.Deferred): self.run_file(guard=guard, opener=lambda *a,**k:response)
        self.assertTrue(response.closed); self.assertFalse((self.root/self.spec['path']).exists())

    def test_root_reserve_before_transport(self):
        with self.assertRaisesRegex(ValueError, 'Root132'): self.run_file(free=lambda: a.RESERVE)
        self.assertEqual(self.calls, [])

    def test_deadline_before_network(self):
        with self.assertRaises(a.Deferred): self.run_file(deadline=0)
        self.assertEqual(self.calls, [])

    def test_truncated_body_refused(self):
        r=Response(b'', headers={'Content-Length':str(len(self.data)),
            'Content-Range':'bytes 0-%d/%d'%(len(self.data)-1,len(self.data))})
        with self.assertRaisesRegex(ValueError, 'Truncated'): self.run_file(opener=lambda *x,**k:r)
        self.assertTrue(r.closed)

    def test_response_overrun_refused(self):
        r=Response(self.data+b'X', headers={'Content-Length':str(len(self.data)),
            'Content-Range':'bytes 0-%d/%d'%(len(self.data)-1,len(self.data))})
        with self.assertRaisesRegex(ValueError, 'overrun'): self.run_file(opener=lambda *x,**k:r)

    def test_foreign_range_refused(self):
        r=Response(self.data, headers={'Content-Length':str(len(self.data)), 'Content-Range':'bytes 1-2/9'})
        with self.assertRaisesRegex(ValueError, 'range'): self.run_file(opener=lambda *x,**k:r)

    def test_content_encoding_refused(self):
        r=Response(self.data);r.headers['Content-Encoding']='gzip'
        with self.assertRaisesRegex(ValueError, 'Encoded'): self.run_file(opener=lambda *x,**k:r)

    def test_missing_content_length_refused(self):
        r=Response(self.data);del r.headers['Content-Length']
        with self.assertRaisesRegex(ValueError, 'length'): self.run_file(opener=lambda *x,**k:r)

    def test_whole_small_200_accepted(self):
        self.run_file(opener=lambda *x,**k:Response(self.data,status=200))

    def test_ignored_range_200_refused(self):
        r=Response(b'123', status=200, headers={'Content-Length':'3'})
        with self.assertRaisesRegex(ValueError, 'ignored'): a.response_contract(r,3,5,6)

    def test_transport_failure_no_retry(self):
        n=[0]
        def op(*x,**k): n[0]+=1;raise OSError('transport')
        with self.assertRaises(OSError): self.run_file(opener=op)
        self.assertEqual(n[0],1)

    def test_absolute_and_traversal_paths_refused(self):
        for name in ['/tmp/foreign','../foreign','Maya-S/../foreign']:
            self.spec['path']=name
            with self.assertRaises(ValueError): self.run_file()

    def test_directory_symlink_refused(self):
        (self.root/'Maya-S').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'alias'): self.run_file()

    def test_file_symlink_refused(self):
        (self.root/'Maya-S').mkdir();(self.root/'Maya-S/test.gguf.partial').symlink_to(self.root/'not-created')
        with self.assertRaisesRegex(ValueError,'symlink'):self.run_file()

    def test_hardlinked_file_refused(self):
        (self.root/'Maya-S').mkdir();q=self.root/'other';q.write_bytes(b'123')
        import os;os.link(q,self.root/'Maya-S/test.gguf.partial')
        with self.assertRaisesRegex(ValueError,'alias'):self.run_file()

    def test_ambiguous_partial_and_final_refused(self):
        (self.root/'Maya-S').mkdir()
        for n in ['test.gguf','test.gguf.partial']:(self.root/'Maya-S'/n).write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'Ambiguous'):self.run_file()

    def test_oversized_retained_partial_refused(self):
        (self.root/'Maya-S').mkdir();(self.root/'Maya-S/test.gguf.partial').write_bytes(self.data+b'x')
        with self.assertRaisesRegex(ValueError,'Oversized'):self.run_file()

    def test_exact_manifest(self):
        d=a.manifest(pathlib.Path(__file__).parent/'ASSET_MANIFEST.json')
        self.assertEqual(len(d['files']),8);self.assertEqual(d['total_bytes'],347445667721)

    def test_changed_manifest_refused(self):
        p=self.root/'changed.json';p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'manifest'):a.manifest(p)

    def test_receipt_temporary_residue_preserved(self):
        p=self.root/'state.json';p.with_name('state.json.tmp').write_text('evidence')
        with self.assertRaisesRegex(ValueError,'residue'):a.emit(p,{'status':'x'})
        self.assertEqual(p.with_name('state.json.tmp').read_text(),'evidence')

    def test_real_localhost_range_and_resume(self):
        data=self.data
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start,end=map(int,self.headers['Range'].removeprefix('bytes=').split('-'))
                body=data[start:end+1]
                self.send_response(206);self.send_header('Content-Length',str(len(body)))
                self.send_header('Content-Range','bytes %d-%d/%d'%(start,end,len(data)));self.end_headers()
                self.wfile.write(body)
            def log_message(self,*args):pass
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            (self.root/'Maya-S').mkdir();(self.root/'Maya-S/test.gguf.partial').write_bytes(data[:5])
            def opener(request,timeout):
                import urllib.request
                req=urllib.request.Request('http://127.0.0.1:%d/test'%server.server_port,headers=request.headers)
                return urllib.request.urlopen(req,timeout=timeout)
            self.run_file(opener=opener)
            self.assertEqual((self.root/self.spec['path']).read_bytes(),data)
        finally:server.shutdown();thread.join(2);server.server_close()

    def test_real_localhost_read_timeout_closes_no_publish(self):
        release=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(206);self.send_header('Content-Length','21')
                self.send_header('Content-Range','bytes 0-20/21');self.end_headers();self.wfile.flush()
                release.wait(2)
            def log_message(self,*args):pass
        self.assertEqual(len(self.data),21)
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            def opener(request,timeout):
                import urllib.request
                req=urllib.request.Request('http://127.0.0.1:%d/test'%server.server_port,headers=request.headers)
                return urllib.request.urlopen(req,timeout=.05)
            with self.assertRaises(TimeoutError):self.run_file(opener=opener)
            self.assertFalse((self.root/self.spec['path']).exists())
        finally:release.set();server.shutdown();thread.join(2);server.server_close()

    def test_blocking_read_crossing_deadline_not_written(self):
        now=[0.0]
        class Late(Response):
            def read1(self,n):now[0]=20.;return super().read1(n)
        with self.assertRaises(a.Deferred):self.run_file(opener=lambda *x,**k:Late(self.data),deadline=10,clock=lambda:now[0])
        self.assertEqual((self.root/'Maya-S/test.gguf.partial').stat().st_size,0)

    def test_guard_rate_not_per_byte(self):
        counts=[0]
        def guard():counts[0]+=1
        self.run_file(guard=guard,clock=lambda:0.)
        self.assertEqual(counts[0],4)

    def test_inventory_foreign_file_refused(self):
        (self.root/'Maya-S').mkdir();(self.root/'Maya-S/unknown').write_text('x')
        with self.assertRaisesRegex(ValueError,'Foreign'):a.retained_inventory(self.root,[self.spec])

    def test_inventory_parent_alias_refused(self):
        (self.root/'Maya-S').symlink_to(self.root,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'alias'):a.retained_inventory(self.root,[self.spec])

    def test_inventory_exact_partial_count(self):
        (self.root/'Maya-S').mkdir();(self.root/'Maya-S/test.gguf.partial').write_bytes(b'abc')
        self.assertEqual(a.retained_inventory(self.root,[self.spec]),3)

    def test_selected_gate_busy_before_binding_capture(self):
        state={'decode_optimization_current':{'selected_identity':{'start_binding':{'native_pid':1}}}}
        host=mock.Mock();host.idle.return_value=False
        rt=mock.Mock();rt.__file__=a.E/'decode-optimization-20261028/iq2s-persistent-v1/model-v1/iq2s_model_runtime.py'
        rt.phase_keys_free.return_value=True;rt.current_binding.return_value={'native_pid':1}
        rt.support.return_value=(mock.Mock(ChunkProductionHost=mock.Mock(return_value=host)),None)
        with mock.patch.dict('sys.modules',{'iq2s_model_runtime':rt}),mock.patch.object(a,'digest',side_effect=lambda p:a.RUNTIME_PINS[pathlib.Path(p).name]),mock.patch.object(pathlib.Path,'read_text',return_value=json.dumps(state)):
            with self.assertRaises(a.Deferred):a.SelectedGate()
        host.guard_binding.assert_not_called()

    def test_selected_gate_phase_before_support_import_use(self):
        rt=mock.Mock();rt.__file__=a.E/'decode-optimization-20261028/iq2s-persistent-v1/model-v1/iq2s_model_runtime.py'
        rt.phase_keys_free.return_value=False
        with mock.patch.dict('sys.modules',{'iq2s_model_runtime':rt}),mock.patch.object(a,'digest',side_effect=lambda p:a.RUNTIME_PINS[pathlib.Path(p).name]),mock.patch.object(pathlib.Path,'read_text',return_value='{}'):
            with self.assertRaises(a.Deferred):a.SelectedGate()
        rt.support.assert_not_called()

    def test_selected_gate_foreign_origin_refused(self):
        rt=mock.Mock();rt.__file__='/tmp/foreign.py'
        with mock.patch.dict('sys.modules',{'iq2s_model_runtime':rt}),mock.patch.object(a,'digest',side_effect=lambda p:a.RUNTIME_PINS[pathlib.Path(p).name]):
            with self.assertRaisesRegex(ValueError,'origin'):a.SelectedGate()

    def test_qualification_missing_explicit_pin_refused(self):
        with self.assertRaisesRegex(ValueError,'pin'):a.qualification(self.root/'none','')

    def test_qualification_exact_source_names_required(self):
        p=self.root/'q';p.write_text(json.dumps({'both_hosts_passed':True,'manual_review_passed':True,'sources':{}}))
        with self.assertRaisesRegex(ValueError,'source map'):a.qualification(p,a.digest(p))

    def test_main_does_not_touch_production_lock(self):
        root=self.root/'decode-optimization-20261028/maya-s-comparison-v1';root.mkdir(parents=True)
        gate=mock.Mock();gate.host.start_binding={'native_pid':1}
        data={'files':[],'total_bytes':0}
        with mock.patch.object(a,'HERE',root),mock.patch.object(a,'E',self.root),mock.patch.object(a,'manifest',return_value=data),mock.patch.object(a,'qualification'),mock.patch.object(a,'SelectedGate',return_value=gate),mock.patch.object(a.shutil,'disk_usage',return_value=mock.Mock(free=a.RESERVE+10000000)),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(a.main('0'*64),0)
        self.assertFalse((self.root.parent/'experiment.lock').exists())
        self.assertEqual(len(list(root.glob('acquisition-attempt-*'))),1)

    def test_main_busy_has_no_owned_metadata_mutation(self):
        root=self.root/'decode-optimization-20261028/maya-s-comparison-v1';root.mkdir(parents=True)
        with mock.patch.object(a,'HERE',root),mock.patch.object(a,'E',self.root),mock.patch.object(a,'manifest',return_value={'files':[]}),mock.patch.object(a,'qualification'),mock.patch.object(a,'SelectedGate',side_effect=a.Deferred('busy')):
            with self.assertRaises(a.Deferred):a.main('0'*64)
        self.assertEqual(list(root.iterdir()),[])

    def test_main_transport_hold_nonzero_and_separate_receipt(self):
        root=self.root/'decode-optimization-20261028/maya-s-comparison-v1';root.mkdir(parents=True)
        gate=mock.Mock();gate.host.start_binding={'native_pid':1}
        with mock.patch.object(a,'HERE',root),mock.patch.object(a,'E',self.root),mock.patch.object(a,'manifest',return_value={'files':[self.spec],'total_bytes':21}),mock.patch.object(a,'qualification'),mock.patch.object(a,'SelectedGate',return_value=gate),mock.patch.object(a.shutil,'disk_usage',return_value=mock.Mock(free=a.RESERVE+10000000)),mock.patch.object(a,'acquire_file',side_effect=OSError('connection')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(a.main('0'*64),1)
        receipts=list(root.glob('acquisition-attempt-*'));self.assertEqual(len(receipts),1)
        self.assertEqual(json.loads(receipts[0].read_text())['returncode'],1)


if __name__ == '__main__': unittest.main(verbosity=2)
