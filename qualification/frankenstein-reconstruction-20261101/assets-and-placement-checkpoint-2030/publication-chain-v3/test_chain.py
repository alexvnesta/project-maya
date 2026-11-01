"""Small metadata/lock/receipt fixtures. No mass weight, model or network work."""
import copy
import fcntl
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import chain as c


class Publication(unittest.TestCase):
    def write(self,q,path,value):
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value));q['files'][str(path)]=c.sha(path);return str(path)

    def test_raw_source_pin_cannot_be_replaced_by_passed_summary(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'source.py';p.write_text('reviewed source')
            q={'files':{str(p):c.sha(p)}};c.pinned(q,p)
            p.write_text('changed source')
            with self.assertRaises(ValueError):c.pinned(q,p)
            with self.assertRaises(ValueError):c.pinned({'files':{}},p)

    def test_controller_exit_is_bound_to_actual_pid_and_clean_zero(self):
        c.clean_exit({'pid':123,'returncode':0,'error':None,'cleanup':[]},123)
        for key,value in (('pid',124),('returncode',1),('returncode',None),('error','fault'),('cleanup',['fault'])):
            row=dict(pid=123,returncode=0,error=None,cleanup=[]);row[key]=value
            with self.assertRaises(ValueError):c.clean_exit(row,123)
        self.check_bounded_join_finalize_child_identity_limits_and_cleanup()

    def test_exact_owned_groups_require_complete_clean_zero_and_current_absence(self):
        row={'passed':True,'pending_spawn':None,'cleanup_faults':[],
             'children':[{'name':'join','pid':123,'pgid':123,'returncode':0,'group_absent':True}]}
        with patch.object(c,'absent',return_value=True):self.assertEqual(c.absence_contract(row),{123})
        for key,value in (('pending_spawn','uncaptured'),('cleanup_faults',['fault']),('children',[])):
            with self.assertRaises(ValueError):c.absence_contract(dict(row,**{key:value}))
        with patch.object(c,'absent',return_value=False),self.assertRaises(ValueError):c.absence_contract(row)

    def check_bounded_join_finalize_child_identity_limits_and_cleanup(self):
        child={'pid':123,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':2.}
        actual={'pid':123,'ppid':122,'pgid':123,'cpu':[30,30],'as':[512*2**20]*2,'nice':15,
                'environment':c.DATA_ENV,'isolated':True,'dont_write_bytecode':True}
        with patch.object(c,'absent',return_value=True):
            self.assertEqual(c.data_child(child,actual,122),123)
            for key,value in (('cpu',[120,120]),('as',[4*2**30]*2),('pgid',124),('environment',{})):
                with self.assertRaises(ValueError):c.data_child(child,dict(actual,**{key:value}),122)
            with self.assertRaises(ValueError):c.data_child(dict(child,returncode=1),actual,122)

    def test_existing_writer_lock_must_be_free_and_same_inode(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t).resolve()/'acquisition.lock';p.write_bytes(b'')
            lock={'path':str(p),'fingerprint':c.fingerprint(p)}
            with c.writer_free(lock):pass
            with p.open('rb') as owner:
                fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(ValueError):
                    with c.writer_free(lock):pass
                fcntl.flock(owner,fcntl.LOCK_UN)
            p.unlink();p.write_bytes(b'replaced')
            with self.assertRaises(ValueError):
                with c.writer_free(lock):pass

    def test_postpublication_fingerprint_and_published_inode_bound_to_raw_result(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();q={'files':{}};artifact=root/'payload';artifact.write_bytes(b'small')
            result=self.write(q,root/'result.json',{'bytes':5,'sha256':'published'})
            row={'schema':'s2-publication-fingerprints-v1','kind':'bounded-overlay-join',
                'source_result_path':result,'source_result_sha256':q['files'][result],
                'files':{str(artifact):{'fingerprint':c.fingerprint(artifact),'published_inode':c.fingerprint(artifact)[:3]}}}
            path=self.write(q,root/'fingerprints.json',row);g={'kind':'bounded-overlay-join','publication_snapshot':path}
            c.snapshot(q,g,result)
            artifact.write_bytes(b'modified')
            with self.assertRaises(ValueError):c.snapshot(q,g,result)

    def test_selected_inventory_is_exact_seven_including_drafter_vision_engram(self):
        state={'pack_files':['DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XS-%05d-of-00004.gguf'%i for i in range(1,5)]+
            ['../shared/DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf','../shared/dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf',
             '../../reliability-optimization-20261025/vision-assets-1017/vision.bin'],
            'model_dir':str(c.R/'models/ista-iq2-xs'),'pack':str(c.E/'pack-native-vision-v1'),
            'storage_geometry':{'layers':43,'experts_per_layer_profile':384}}
        self.assertEqual(len(c.selected_inventory(state)),7)
        self.assertTrue(c.selected_inventory(state)[5].endswith('/models/shared/dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf'))
        for key,value in (('pack_files',state['pack_files'][:-1]),('model_dir','/foreign')):
            with self.assertRaises(ValueError):c.selected_inventory(dict(state,**{key:value}))

    def test_public_READY_requires_actual_complete_raw_stop_done(self):
        good=b'data: {"choices":[{"delta":{"content":"READY"},"finish_reason":null}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        c.public_READY(good)
        for wrong in (good.replace(b'READY',b'WRONG'),good.replace(b'"stop"',b'"length"'),
                      good.replace(b'data: [DONE]',b''),good+b'data: [DONE]\n'):
            with self.assertRaises(ValueError):c.public_READY(wrong)

    def test_selected_chain_requires_raw_restore_window_READY_topology_and_current_seven_files(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();e=root/'reliability-optimization-20261025';pack=e/'pack-native-vision-v1'
            q={'files':{},'selected_binding':{'invocation':'a'*32,'main_pid':122,'native_pid':123,'native_start_ticks':55}}
            with patch.object(c,'R',root),patch.object(c,'E',e):
                names=(['DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XS-%05d-of-00004.gguf'%i for i in range(1,5)]+
                    ['../shared/DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf','../shared/dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf',
                     '../../reliability-optimization-20261025/vision-assets-1017/vision.bin'])
                # Tiny stand-ins test metadata/fingerprint custody, not content
                # qualification of any real selected model or release.
                metadata={'pack_files':names,'model_dir':str(root/'models/ista-iq2-xs'),'pack':str(pack),
                          'storage_geometry':{'layers':43,'experts_per_layer_profile':384}}
                for name in c.selected_inventory(metadata):
                    p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'synthetic-selected')
                pack.mkdir(parents=True)
                for name in ('ds4.txt','tensors.txt'):
                    p=pack/name;p.write_text('small pinned metadata');q['files'][str(p)]=c.sha(p)
                metadata.update(ds4_txt_sha256=q['files'][str(pack/'ds4.txt')],tensors_txt_sha256=q['files'][str(pack/'tensors.txt')])
                release=self.write(q,root/'release.json',{'files':{str(c.D/'bin/maya-ds4'):c.NATIVE92}})
                state=self.write(q,root/'pack-state.json',metadata)
                window=self.write(q,root/'window.json',{'test_returncode':0,'maintenance_held':True,
                    'maintenance_resume_allowed':True,'maintenance_root_window':'20261025T032914Z.json'})
                telemetry=self.write(q,root/'window-last.json',{'kernel_capture_returncode':0,'kernel_fault_lines':[]})
                identity={'native_sha256':c.NATIVE92,'config_sha256':c.CONFIG43,'context':1048576,'output_default':262144,
                    'prefill_chunk':4096,'Q8':[1,1],'DSpark':True,'images':True,'TP':1,'all_CPU_experts_RAM':True,
                    'native_pid':123,'start_binding':q['selected_binding']}
                public={'unauthenticated_models':401,'authenticated_models':200,'content':'READY','finish':'stop',
                        'SSE_done':True,'known_answer_passed':True}
                result={'status':'S2_PLACEMENT_SELECTED4096_RESTORED','window':window,
                        'verified':{'passed':True,'selected_identity':identity,'public':public}}
                restoration=self.write(q,root/'restoration.json',result)
                sse=root/'public.txt';sse.write_text('data: {"choices":[{"delta":{"content":"READY"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n')
                q['files'][str(sse)]=c.sha(sse)
                files={n:{'fingerprint':c.fingerprint(n),'published_inode':c.fingerprint(n)[:3]} for n in c.selected_inventory(metadata)}
                snap=self.write(q,root/'snapshot.json',{'schema':'s2-publication-fingerprints-v1','kind':'selected-publication',
                    'source_result_path':restoration,'source_result_sha256':q['files'][restoration],
                    'selected_binding':q['selected_binding'],'files':files})
                g={'kind':'selected-publication','release':release,'restoration':restoration,'window':window,
                   'window_telemetry':telemetry,'public_sse':str(sse),'pack_state':state,'publication_snapshot':snap}
                with patch.object(c,'RELEASE',q['files'][release]),patch.object(c,'PACK_STATE_A',q['files'][state]):
                    _,hashes=c.selected_group(q,g);self.assertEqual(set(hashes.values()),{None})
                    wrong=copy.deepcopy(result);wrong['verified']['selected_identity']['output_default']=16384
                    self.write(q,Path(restoration),wrong)
                    with self.assertRaises(ValueError):c.selected_group(q,g)

    def test_selected_unknown_SHA_allowed_but_new_overlay_requires_real_SHA(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();q={'files':{},'large_verified':{},'artifact_chains':{}}
            artifact=root/'selected';artifact.write_bytes(b'old-qualified')
            fp=c.fingerprint(artifact);snap={'files':{str(artifact):{'fingerprint':fp}}}
            g={'kind':'selected-publication'}
            for field in ('release','restoration','window','window_telemetry','public_sse','pack_state','publication_snapshot'):
                g[field]=self.write(q,root/(field+'.json'),{})
            g['raw_paths']=[g[k] for k in g if k!='kind']
            q['artifact_chains']['selected']=g;q['large_verified'][str(artifact)]={'chain':'selected','sha256':None,'fingerprint':fp}
            with patch.object(c,'selected_group',return_value=(snap,{str(artifact):None})):
                self.assertIsNone(c.validate_groups(q)[str(artifact)]['sha256'])
            folder=c.Q/'iq3s-assembly-v3/assembly-FIRST'
            overlay={'kind':'bounded-overlay-join','source':'source','qualification':'qualification','result':'result',
                     'controller_start':'start','controller_exit':'exit','publication_snapshot':'snapshot'}
            needed=[overlay[n] for n in ('source','qualification','result','controller_start','controller_exit','publication_snapshot')]
            needed += [str(folder/n) for n in ('attempt.json','supervision.json','absence.json',
                                              'finalize.child.json','finalize.observed.json','finalize.DONE.json')]
            needed += [str(folder/(str(i)+suffix)) for i in range(30) for suffix in ('.child.json','.observed.json','.DONE.json')]
            # Pinned/read methods injected for small policy fixture; no real Q
            # files are written or original source qualifications bypassed in run.
            overlay['raw_paths']=needed;q['artifact_chains']={'selected':overlay}
            with patch.object(c,'pinned',return_value=root/'result.json'),patch.object(c,'overlay_group',return_value=(snap,{str(artifact):None})):
                with self.assertRaises(ValueError):c.validate_groups(q,source_check=lambda *args:None)

    def hops(self,size,pid=200,parent=100):
        out=[];offset=0
        for i in range((size+4*2**30-1)//(4*2**30)):
            current=pid if i==0 else pid+100+i
            previous=parent if i==0 else out[-1]['observed']['pid']
            end=min(size,offset+4*2**30)
            row={'observed':{'pid':current,'ppid':previous,'pgid':pid,'cpu':[30,30],'as':[512*2**20]*2,'nice':15,
                 'isolated':True,'dont_write_bytecode':True,'CUDA_VISIBLE_DEVICES':''},'offset':offset,'end':end,
                 'own_user_seconds':.1,'own_system_seconds':.1}
            if end<size:row.update(waited_child_pid=pid+100+i+1,waited_child_returncode=0)
            out.append(row);offset=end
        return out

    def test_inherited_normal_hash_hops_require_exact_coverage_limits_and_child_wait0(self):
        for size in (19464192000,35157299200):
            rows=self.hops(size);c.hash_hops(rows,size,200,100)
            for mode in ('hole','pgid','limit','exit','count'):
                wrong=copy.deepcopy(rows)
                if mode=='hole':wrong[1]['offset']+=1
                elif mode=='pgid':wrong[1]['observed']['pgid']=999
                elif mode=='limit':wrong[1]['observed']['cpu']=[60,60]
                elif mode=='exit':wrong[0]['waited_child_returncode']=1
                else:wrong.pop()
                with self.subTest(mode=mode,size=size),self.assertRaises(ValueError):c.hash_hops(wrong,size,200,100)

    def test_UNKNOWN_outer_exit_allowed_only_base_with_explicit_observer_and_absent_PID(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();q={'files':{}};source=self.write(q,root/'source.json',{'source':'pinned'})
            row={'pid':123,'source_path':source,'source_sha256':q['files'][source],'returncode':None,'status':'UNKNOWN',
                 'start_ticks':55,'start_ticks_status':'RECORDED','limitation':'Terminal reports intended returncode0 before print; actual outer exit unobserved'}
            observer=self.write(q,root/'observer.json',row);g={'kind':'base-acquisition-publication','outer_exit_observer':observer}
            with patch.object(c,'absent',return_value=True):c.outer_exit_contract(q,g,123,Path(source))
            with patch.object(c,'absent',return_value=False),self.assertRaises(ValueError):c.outer_exit_contract(q,g,123,Path(source))
            start=self.write(q,root/'start.json',{'pid':123,'supervisor_pid':122,'argv':['python','-I','-B',source]})
            exit=self.write(q,root/'exit.json',dict(row,supervisor_pid=122,argv=['python','-I','-B',source],error=None,cleanup=[]))
            for kind in ('bounded-overlay-join','bounded-native-finalize'):
                g={'kind':kind,'controller_start':start,'controller_exit':exit}
                with self.assertRaises(ValueError):c.outer_exit_contract(q,g,123,Path(source))

    def test_actual_new_assembly_schema_binds31groups3840records_and_logicalresource_to_newbuilder(self):
        from types import SimpleNamespace
        folder=c.Q/'iq3s-assembly-v3/assembly-FIRST';source=str(folder.parent/'assembly.py')
        artifact=str(c.Q/'iq3s-bulk-v1/conversion-FIRST/overlay.iq3s');pid=100;size=19464192000
        identity=[1,2,size];fp=identity+[3,4];qualification='new-assembly-qualification'
        records=[{'target_offset':i*5068800,'target_bytes':5068800,'index':i} for i in range(3840)]
        aq={'original_controller_pid':99};data={};groups=[]
        for index in range(30):
            begin,end=index*128,(index+1)*128;unitpid=1000+index
            child={'pid':unitpid,'mode':index,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':1.,'wait4_usage':{'user_seconds':.1}}
            observed={'pid':unitpid,'ppid':pid,'pgid':unitpid,'cpu':[30,30],'as':[512*2**20]*2,'nice':15,'environment':c.DATA_ENV,'isolated':True}
            done={'range':[begin,end],'output_identity':identity,'parts':[{'index':n,'record':records[n],'sha256':'a'*64,
                  'source_fingerprint':[7,n,5068800,8,9]} for n in range(begin,end)]}
            for suffix,value in (('.child.json',child),('.observed.json',observed),('.DONE.json',done)):data[str(folder/(str(index)+suffix))]=value
            groups.append({'name':str(index),'pid':unitpid,'pgid':unitpid,'returncode':0,'group_absent':True})
        finalpid=1030;hops=self.hops(size,finalpid,pid)
        final={'sha256':'a'*64,'bytes':size,'source_inode':identity,'complete':True,'parts':3840,'full_SHA_passes':1,
               'bounded_hash_hops':hops,'aggregate_CPU_can_exceed30_each_process_CPU30':True}
        data[str(folder/'finalize.DONE.json')]=final
        data[str(folder/'finalize.child.json')]={'pid':finalpid,'mode':'finalize','returncode':0,'error':None,'cleanup':[],
                                               'elapsed_seconds':1.,'wait4_usage':{'user_seconds':.1}}
        data[str(folder/'finalize.observed.json')]={'pid':finalpid,'ppid':pid,'pgid':finalpid,'cpu':[30,30],'as':[512*2**20]*2,
                                                  'nice':15,'environment':c.DATA_ENV,'isolated':True}
        groups.append({'name':'finalize','pid':finalpid,'pgid':finalpid,'returncode':0,'group_absent':True})
        data[str(folder/'attempt.json')]={'controller_pid':pid,'output_identity':identity,'original_outer_exit_status':'UNKNOWN','known_original_join_exit':-9}
        data[str(folder/'absence.json')]={'passed':True,'pending_spawn':None,'cleanup_faults':[],'children':groups}
        data[str(folder/'supervision.json')]={'passed':True,'error':None,'owned_claim_released':True}
        result=dict(final,passed=True,artifact_path=artifact,producer_source=source,producer_qualification_sha256='qpin',qualification_sha256='qpin',
            original_outer_exit_status='UNKNOWN',known_original_join_exit=-9,original_failure_regraded=False,
            separate_artifact_acceptance_required=True,model_executed=False,production_changed=False,fingerprint=fp)
        data[str(folder/'result.json')]=result
        argv=['python','-I','-B',source,'run','qpin']
        data['start']={'pid':pid,'supervisor_pid':98,'argv':argv}
        data['exit']={'pid':pid,'supervisor_pid':98,'argv':argv,'returncode':0,'error':None,'cleanup':[],
                      'actual_wait_observed':True,'retry':False,'target_signals_sent':0}
        data['snapshot']={'schema':'s2-publication-fingerprints-v1','kind':'bounded-overlay-join',
            'source_result_path':str(folder/'result.json'),'source_result_sha256':'resultpin',
            'files':{artifact:{'fingerprint':fp,'published_inode':identity}}}
        q={'files':{qualification:'qpin',str(folder/'result.json'):'resultpin',str(c.Q/'launch-custody-v1/launch.py'):c.LAUNCH_SHA}}
        g={'result':str(folder/'result.json'),'artifact':artifact,'source':source,'qualification':qualification,
           'kind':'bounded-overlay-join','controller_start':'start','controller_exit':'exit','publication_snapshot':'snapshot'}
        module=SimpleNamespace(original_failure=lambda aq:99,ranges=lambda:[(i*128,(i+1)*128) for i in range(30)],
            proof_loader=lambda *args:lambda n:({'sha256':'a'*64},None,None))
        real_fingerprint=c.fingerprint
        def fpof(path):
            if Path(path).name=='launch.py':return real_fingerprint(path)
            return fp if str(path)==artifact else [7,int(Path(path).stem),5068800,8,9]
        with patch.object(c,'raw',side_effect=lambda q,path:data[str(path)]),patch.object(c,'fingerprint',side_effect=fpof),patch.object(c,'absent',return_value=True):
            _,hashes=c.overlay_group(q,g,(module,aq,records));self.assertEqual(hashes,{artifact:'a'*64})
            result['producer_source']='old-bulk-producer'
            with self.assertRaises(ValueError):c.overlay_group(q,g,(module,aq,records))

    def test_missing_raw_group_fails_before_source_import(self):
        g={'kind':'selected-publication','raw_paths':['only-one']}
        for n in ('release','restoration','window','window_telemetry','public_sse','pack_state','publication_snapshot'):g[n]=n
        with self.assertRaises(ValueError):c.validate_groups({'large_verified':{},'artifact_chains':{'x':g},'files':{}})

    def test_own_CPU_receipt_needs_exact_source_ids_resources_and_exit(self):
        review={'source_map':{'chain.py':'pin'},'input_map':{'qualified_supervisor':c.DRIVER_SHA},'test_ids':['one']}
        actual={'pid':123,'pgid':123,'ppid':122,'platform':'linux','cpu':[30,30],'as':[512*2**20]*2,
                'nice':15,'environment':c.ENV,'dont_write_bytecode':True}
        proof=dict(review,passed=True,returncode=0,failures=0,errors=0,controls=1,observed=actual,supervisor_pid=122,isolated=True)
        child={'pid':123,'returncode':0,'error':None,'cleanup':[],'elapsed_seconds':1.}
        c.cpu_contract(proof,child,review,'linux')
        for key,value in (('controls',0),('failures',1),('returncode',1),('source_map',{}),('isolated',False)):
            with self.assertRaises(ValueError):c.cpu_contract(dict(proof,**{key:value}),child,review,'linux')
        with self.assertRaises(ValueError):c.cpu_contract(proof,dict(child,cleanup=['survived']),review,'linux')


if __name__=='__main__':unittest.main(verbosity=2)
