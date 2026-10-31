"""FIRST exact-source CPU proof, child-only bounds. No CUDA compilation or GPU."""
import argparse,ast,json,os,pathlib,resource,signal,subprocess,sys,time,unittest
import recovery as r
def ids():
 t=ast.parse((r.HERE/'test_recovery.py').read_text())
 return sorted('test_recovery.'+c.name+'.'+f.name for c in t.body if isinstance(c,ast.ClassDef) for f in c.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))
def main(child=False):
 review=r.reviewed();test_ids=ids();r.require(review['test_ids']==test_ids,'test inventory changed')
 # One immutable read-only input: original fully reviewed build recipe metadata.
 inputs={'prepare-FIRST/plan.json':r.sha(r.HERE.parent/'prepare-FIRST/plan.json')}
 r.require(inputs==review['input_sha256'],'recipe metadata changed')
 out=r.HERE/('CPU-FIRST-'+sys.platform)
 if child:
  suite=unittest.defaultTestLoader.loadTestsFromName('test_recovery');actual=[]
  def walk(s):
   for x in s:
    if isinstance(x,unittest.TestSuite):walk(x)
    else:actual.append(x.id())
  walk(suite);r.require(actual==test_ids,'actual test IDs differ')
  result=unittest.TextTestRunner(verbosity=2).run(suite)
  cpp=out/'host-contract'
  compiler=['c++','-O2','-std=c++17','-I'+str(r.HERE),str(r.HERE/'test_contract.cpp'),'-o',str(cpp)]
  c=subprocess.run(compiler,capture_output=True,text=True,timeout=20);(out/'CXX-compile.log').write_text(c.stdout+c.stderr);r.require(c.returncode==0,'host CXX compile')
  p=subprocess.run([str(cpp)],capture_output=True,text=True,timeout=10);(out/'CXX-run.log').write_text(p.stdout+p.stderr)
  passed=result.wasSuccessful() and p.returncode==0 and p.stdout=='ALL 19 HOST_CONTRACT controls passed\n'
  r.require(r.source_map()==review['source_sha256'],'source changed during proof')
  r.require({'prepare-FIRST/plan.json':r.sha(r.HERE.parent/'prepare-FIRST/plan.json')}==inputs,'recipe changed during proof')
  r.new(out/'receipt.json',{'passed':passed,'source_sha256':r.source_map(),'input_sha256':inputs,'test_ids':test_ids,'controls':result.testsRun,'CXX_controls':19,'CXX_compile_returncode':c.returncode,'CXX_run_returncode':p.returncode,'compiler_argv':compiler,'GPU_execution':False,'CUDA_compilation':False,'model_execution':False})
  return 0 if passed else 1
 if sys.platform=='linux':r.guard()
 r.require(sys.platform in ('darwin','linux') and not out.exists() and not out.is_symlink(),'FIRST proof namespace')
 out.mkdir();env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MALLOC_ARENA_MAX='1',PYTHONDONTWRITEBYTECODE='1')
 process=None;error=None;cleanup=[];code=None
 with (out/'child.log').open('x') as log:
  try:
   process=subprocess.Popen([sys.executable,'-B',str(r.HERE/'qualify_cpu.py'),'--child'],env=env,cwd=r.HERE,start_new_session=True,preexec_fn=lambda:r.limits(30,512),stdout=log,stderr=subprocess.STDOUT)
   code=process.wait(timeout=90)
  except BaseException as exc:error=repr(exc)
  finally:
   if process:
    for sig in (signal.SIGTERM,signal.SIGKILL):
     try:os.killpg(process.pid,sig)
     except ProcessLookupError:pass
     except BaseException as exc:cleanup.append(repr(exc))
    try:process.wait(timeout=10)
    except BaseException as exc:cleanup.append(repr(exc))
    code=process.returncode
    try:
     if not r.group_gone(process.pid):cleanup.append('Owned CPU group survived cleanup')
    except BaseException as exc:cleanup.append(repr(exc))
 r.new(out/'child.json',{'pid':process.pid if process else None,'returncode':code,'error':error,'cleanup_errors':cleanup,'CPU_s':30,'wall_s':90,'nice':15,'CUDA_hidden':True,'Linux_AS_MiB':512 if sys.platform=='linux' else None})
 r.require(code==0 and error is None and cleanup==[],'FIRST CPU HOLD')
 r.reviewed();r.require({'prepare-FIRST/plan.json':r.sha(r.HERE.parent/'prepare-FIRST/plan.json')}==inputs,'recipe changed after proof')
 if sys.platform=='linux':r.guard()
 print(json.dumps({'passed':True,'Python_controls':len(test_ids),'CXX_controls':19,'host':sys.platform}))
 return 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--child',action='store_true');a=p.parse_args();raise SystemExit(main(a.child))
