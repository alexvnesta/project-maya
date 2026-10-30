"""Post-fault guard, transport/PID ownership and fail-closed result tests. No GPU."""
import copy,json,pathlib,subprocess,tempfile,unittest
from unittest.mock import patch,MagicMock
import recovery as r
class Contracts(unittest.TestCase):
 def setUp(self):
  self.s={'production_temporarily_stopped':True,'current_native_pid':None,'decode_optimization_current':{'status':'STOPPED_FOR_OFFLINE_DIAGNOSIS'}}
  self.u={'ActiveState':'failed','InvocationID':'27f9b1951f494c47a5f6de81f7323ba6','MainPID':'0','Result':'exit-code'}
 def good(self,**kw):
  args=dict(s=self.s,unit=self.u,gpus=[],used=[0,0],active=[]);args.update(kw);return r.stopped_contract(**args)
 def test_stopped(self):self.assertTrue(self.good())
 def test_foreign_unit(self):
  for k,v in [('ActiveState','active'),('InvocationID','different'),('MainPID','7'),('Result','success')]:
   u=dict(self.u);u[k]=v
   with self.assertRaises(ValueError):self.good(unit=u)
 def test_missing_unit_field(self):
  for k in self.u:
   u=dict(self.u);del u[k]
   with self.assertRaises(ValueError):self.good(unit=u)
 def test_extra_unit(self):
  with self.assertRaises(ValueError):self.good(unit=dict(self.u,extra='x'))
 def test_nonstopped(self):
  self.s['production_temporarily_stopped']=False
  with self.assertRaises(ValueError):self.good()
 def test_live_native(self):
  self.s['current_native_pid']=1
  with self.assertRaises(ValueError):self.good()
 def test_wrong_lineage(self):
  self.s['decode_optimization_current']['status']='OK'
  with self.assertRaises(ValueError):self.good()
 def test_no_lineage(self):
  del self.s['decode_optimization_current']
  with self.assertRaises(ValueError):self.good()
 def test_phase(self):
  for k in ('active_private_phase','active_GPU_phase','active_gpu_experiment','private_window','active_cpu_build','production_restore_in_progress','production_verification_pending'):
   with self.assertRaises(ValueError):self.good(s=dict(self.s,**{k:{'owner':1}}))
 def test_gpu_owner(self):
  with self.assertRaises(ValueError):self.good(gpus=['123'])
 def test_gpu_usage(self):
  for x in ([11,0],[0,-1],[0],[0,False],[0,'0']):
   with self.assertRaises(ValueError):self.good(used=x)
 def test_competing(self):
  with self.assertRaises(ValueError):self.good(active=['router'])
 def test_properties(self):self.assertEqual(r.properties('A=b\nC=d\n'),{'A':'b','C':'d'})
 def test_duplicate_properties(self):
  with self.assertRaises(ValueError):r.properties('A=b\nA=c')
 def test_malformed_properties(self):
  with self.assertRaises(ValueError):r.properties('not a property')
 def test_exact_case_inventory(self):
  self.assertEqual(len(r.expected_lines(0)),13);self.assertEqual(len(set(r.expected_lines(0))),13)
 def test_result(self):self.assertEqual(r.result_contract('\n'.join(r.expected_lines(0))+'\n',0,0),{'device':0,'cases':12,'exit':0})
 def test_other_device(self):self.assertEqual(r.result_contract('\n'.join(r.expected_lines(1)),0,1)['device'],1)
 def test_partial(self):
  with self.assertRaises(ValueError):r.result_contract('\n'.join(r.expected_lines(0)[:-1]),0,0)
 def test_extra(self):
  with self.assertRaises(ValueError):r.result_contract('\n'.join(r.expected_lines(0)+['extra']),0,0)
 def test_reorder(self):
  with self.assertRaises(ValueError):r.result_contract('\n'.join(reversed(r.expected_lines(0))),0,0)
 def test_nonzero(self):
  for c in (1,124,None,False):
   with self.assertRaises(ValueError):r.result_contract('\n'.join(r.expected_lines(0)),c,0)
 def test_wrong_device(self):
  for d in (-1,2,False,'0'):
   with self.assertRaises(ValueError):r.result_contract('\n'.join(r.expected_lines(0)),0,d)
 def test_device_transposition(self):
  with self.assertRaises(ValueError):r.result_contract('\n'.join(r.expected_lines(1)),0,0)
 def test_fresh_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'receipt';r.new(p,{'a':1})
   with self.assertRaises(FileExistsError):r.new(p,{'a':2})
   self.assertEqual(r.read(p),{'a':1})
 def test_nonfinite_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):r.new(pathlib.Path(d)/'receipt',{'a':float('nan')})
 def test_sha(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'empty';p.write_bytes(b'');self.assertEqual(r.sha(p),'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
 def test_compile_plan(self):
  p=r.build_plan();self.assertEqual([x[0] for x in p],['deps','compile','link'])
  self.assertIn('-M',p[0][1]);self.assertIn('-c',p[1][1]);self.assertNotIn('-M',p[1][1])
 def test_original_objects_only(self):
  _,compile,link=r.build_plan();text=' '.join(compile[1]+link[1])
  self.assertNotIn('candidate',text);self.assertNotIn('ds4_model',text)
  self.assertIn('maya-ds4.dir/src/ds4/ds4_gguf.cu.o',text);self.assertIn('maya-ds4.dir/src/ds4/ds4_iq.cu.o',text)
 def test_no_fastmath(self):
  text=' '.join(r.build_plan()[1][1]);self.assertNotIn('use_fast_math',text);self.assertIn('sm_80',text)
 def test_new_source_outputs(self):
  for _,a in r.build_plan():self.assertTrue(a[a.index('-o')+1].startswith(str(r.HERE/'build-FIRST')))
 def test_no_restart_authority(self):
  text=(r.HERE/'recovery.py').read_text();self.assertNotIn("'start','deepseek-hosted",text);self.assertNotIn('Host.idle',text)
 def supervised(self,p,**kw):
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'Popen',return_value=p) as launch,patch.object(r.os,'killpg') as kill,patch.object(r,'group_gone',return_value=True):
   result=r.child(['fake-bounded-child'],pathlib.Path(d),'test',30,512,90,**kw)
   return result,launch.call_args,kill.call_args_list
 def fake(self,code=0):
  p=MagicMock();p.pid=999999;p.returncode=code;p.wait.return_value=code;p.poll.return_value=code;return p
 def test_child_success(self):
  result,args,kill=self.supervised(self.fake());self.assertEqual(result['returncode'],0);self.assertFalse(result['retry']);self.assertEqual(len(kill),2)
 def test_child_environment(self):
  _,args,_=self.supervised(self.fake());env=args.kwargs['env']
  self.assertEqual(env['CUDA_VISIBLE_DEVICES'],'');self.assertEqual(env['OMP_NUM_THREADS'],'1');self.assertEqual(env['OPENBLAS_NUM_THREADS'],'1');self.assertEqual(env['MALLOC_ARENA_MAX'],'1')
 def test_child_group(self):
  _,args,_=self.supervised(self.fake());self.assertTrue(args.kwargs['start_new_session']);self.assertIsNotNone(args.kwargs['preexec_fn'])
 def test_child_failure(self):
  with self.assertRaises(ValueError):self.supervised(self.fake(1))
 def test_child_deadline(self):
  p=self.fake();p.wait.side_effect=[subprocess.TimeoutExpired('test',90),0]
  with self.assertRaises(ValueError):self.supervised(p)
 def test_child_identity_failure(self):
  with self.assertRaises(ValueError):self.supervised(self.fake(),identity=lambda pid,args:(_ for _ in ()).throw(ValueError('wrong PID')))
 def test_child_GPU_inherits_group(self):
  _,args,kill=self.supervised(self.fake(),hidden=False);self.assertFalse(args.kwargs['start_new_session']);self.assertEqual(kill,[])
  self.assertEqual(args.kwargs['env']['STRATA_DS4_Q8_BATCH'],'1');self.assertEqual(args.kwargs['env']['DS4_Q8_CHECK'],'1')
 def test_child_cleanup_failure(self):
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'Popen',return_value=self.fake()),patch.object(r.os,'killpg',side_effect=PermissionError('not ours')):
   with self.assertRaises(ValueError):r.child(['fake'],pathlib.Path(d),'test',30,512,90)
   self.assertGreaterEqual(len(r.read(pathlib.Path(d)/'test-exit.json')['cleanup_errors']),2)
 def test_child_primary_preserved(self):
  p=self.fake(1)
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'Popen',return_value=p),patch.object(r.os,'killpg'),patch.object(r,'group_gone',return_value=True):
   with self.assertRaises(ValueError):r.child(['fake'],pathlib.Path(d),'test',30,512,90)
   self.assertEqual(r.read(pathlib.Path(d)/'test-exit.json')['returncode'],1)
 def test_child_start_refusal(self):
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'Popen',side_effect=OSError('cannot exec')):
   with self.assertRaises(ValueError):r.child(['fake'],pathlib.Path(d),'test',30,512,90)
   receipt=r.read(pathlib.Path(d)/'test-exit.json');self.assertIsNone(receipt['pid']);self.assertIn('cannot exec',receipt['error'])
 def test_surviving_descendant(self):
  with tempfile.TemporaryDirectory() as d,patch.object(r.subprocess,'Popen',return_value=self.fake()),patch.object(r.os,'killpg'),patch.object(r,'group_gone',return_value=False):
   with self.assertRaises(ValueError):r.child(['fake'],pathlib.Path(d),'test',30,512,90)
   self.assertIn('Owned child group survived cleanup',r.read(pathlib.Path(d)/'test-exit.json')['cleanup_errors'])
 def test_group_gone(self):
  with patch.object(r.os,'killpg',side_effect=ProcessLookupError):self.assertTrue(r.group_gone(999999))
 def test_group_survives(self):
  with patch.object(r.os,'killpg'),patch.object(r.time,'monotonic',side_effect=[0,6]):self.assertFalse(r.group_gone(999999))
 def test_dependencies(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);f=p/'input';f.write_text('x');dep=p/'deps';dep.write_text('out: '+str(f));pins={str(f):r.sha(f)}
   self.assertEqual(r.dependency_pins(dep,{'files':pins},{}),pins)
 def test_dependency_unknown(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);f=p/'input';f.write_text('x');dep=p/'deps';dep.write_text('out: '+str(f))
   with self.assertRaises(ValueError):r.dependency_pins(dep,{'files':{}},{})
 def test_dependency_missing(self):
  with tempfile.TemporaryDirectory() as d:
   dep=pathlib.Path(d)/'deps';dep.write_text('out: /unavailable-unowned-input')
   with self.assertRaises(ValueError):r.dependency_pins(dep,{'files':{}},{})
 def test_input_mutation(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'input';p.write_text('x');pins={str(p):r.sha(p)};p.write_text('y')
   with self.assertRaises(ValueError):r.pin_check(pins)
 def entry_data(self):
  argv=[str(r.R/'venv/bin/python3.14'),'-B',str(r.HERE/'recovery.py'),'entry','--admission-pin','abc']
  return {'continued_from':str(r.CLEAN),'mutation_started':True,'admission_mode':'continued-explicit-deepseek-maintenance','command':argv},argv
 def test_entry_command(self):
  w,a=self.entry_data();r.entry_contract(w,a,'abc')
 def test_entry_actual_argv(self):
  w,a=self.entry_data()
  with self.assertRaises(ValueError):r.entry_contract(w,a+['extra'],'abc')
 def test_entry_recorded_argv(self):
  w,a=self.entry_data();w['command']=[]
  with self.assertRaises(ValueError):r.entry_contract(w,a,'abc')
 def test_entry_stale_lineage(self):
  w,a=self.entry_data();w['continued_from']=str(r.FAILED)
  with self.assertRaises(ValueError):r.entry_contract(w,a,'abc')
 def test_entry_completed(self):
  w,a=self.entry_data();w['test_returncode']=0
  with self.assertRaises(ValueError):r.entry_contract(w,a,'abc')
 def test_entry_wrong_admission(self):
  w,a=self.entry_data()
  with self.assertRaises(ValueError):r.entry_contract(w,a,'different')
 def mock_build(self,mode):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);src=p/'health.cu';src.write_text('reviewed source');out=p/'build-FIRST'
   plans=[(n,['fake','-o',str(out/f)]) for n,f in [('deps','health.headers.d'),('compile','health.o'),('link','baseline-health')]]
   calls=[];checks=[]
   def old():
    checks.append(1)
    if mode=='tamper' and len(checks)==6:(out/'health.o').write_text('tampered')
    return {'files':{}}
   def child(argv,folder,label,*bounds):
    calls.append(label)
    if mode=='fail':raise ValueError('first child failed')
    artifact=pathlib.Path(argv[argv.index('-o')+1])
    artifact.write_text('target: '+str(src) if label=='deps' else label)
    if label=='link':(out/'health.link.d').write_text('target: '+str(out/'health.o'))
    return {'returncode':0}
   with patch.object(r,'HERE',p),patch.object(r,'guard'),patch.object(r,'cpu_proofs',return_value={'source_sha256':{'health.cu':r.sha(src)}}),patch.object(r,'old_pins',side_effect=old),patch.object(r,'build_plan',return_value=plans),patch.object(r,'child',side_effect=child):
    if mode=='good':r.build_locked();self.assertTrue(r.read(out/'receipt.json')['passed'])
    else:
     with self.assertRaises(ValueError):r.build_locked()
     self.assertFalse((out/'receipt.json').exists())
   return calls
 def test_build_three_steps(self):self.assertEqual(self.mock_build('good'),['deps','compile','link'])
 def test_build_first_fault_stops(self):self.assertEqual(self.mock_build('fail'),['deps'])
 def test_build_object_tamper_blocks_link(self):self.assertEqual(self.mock_build('tamper'),['deps','compile'])

 def test_actual_link_phony_rules(self):
  names=r.dependencies((r.HERE/'prior-link.d').read_text(),relative_to=r.B)
  self.assertEqual(len(names),36);self.assertEqual(len(names),len(set(names)))
 def test_qualified_parser_identical(self):
  import ast,inspect
  old=ast.parse((r.HERE.parents[2]/'selected_build.py').read_text());new=ast.parse(inspect.getsource(r.dependencies))
  original=next(x for x in old.body if isinstance(x,ast.FunctionDef) and x.name=='dependencies')
  self.assertEqual(ast.dump(original,include_attributes=False),ast.dump(new.body[0],include_attributes=False))
 def test_sync_repair_exact_delta(self):
  source=(r.HERE/'health.cu').read_text()
  added=' // Explicitly finish default-stream initialization before the nonblocking kernel.\n ck(cudaDeviceSynchronize());\n'
  self.assertEqual(source.count(added),1);self.assertEqual(source.replace(added,''),(r.HERE/'prior-health.cu').read_text())
 def test_sync_precedes_original_dispatch(self):
  source=(r.HERE/'health.cu').read_text()
  self.assertLess(source.index('cudaMemcpy(y.p'),source.index('ck(cudaDeviceSynchronize());'))
  self.assertLess(source.index('ck(cudaDeviceSynchronize());'),source.index('require(gg::mv'))
 def test_sync_error_checked(self):
  source=(r.HERE/'health.cu').read_text()
  self.assertIn('static void ck(cudaError_t e) {if(e!=cudaSuccess) throw std::runtime_error',source)
  self.assertIn('ck(cudaDeviceSynchronize());',source);self.assertIn('return 1;',source)
