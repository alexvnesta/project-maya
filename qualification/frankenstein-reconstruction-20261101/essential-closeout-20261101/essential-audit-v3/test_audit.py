import copy
import unittest
import audit as a


class Audit(unittest.TestCase):
    def inputs(self):
        request={'native_pid':123,'ids':[1,2],'max_new':32768,'sampling':{'temperature':1.,'top_p':1.,'seed':1}}
        trace={'native_pid':123,'DONE_observed':True,'error':None,'T_lines':2}
        stats={'generated':2,'prompt_tokens':2,'finish':'stop','prompt_ms':1.,'decode_ms':10.,'reused':0,'drafts_offered':1,'drafts_accepted':0}
        return [request,trace,stats,[{'token':5,'seconds':.1},{'token':6,'seconds':.2}],{'prompt_ids':[1,2],'prompt_tokens':2,'expected_reuse':'zero'},123]

    def test_exact_native_token_sampling_reuse_and_done_observation(self):
        self.assertEqual(a.native_case(*self.inputs())['generated'],2)
        for what in ('pid','cap','done','length','count','reuse','sampling','draft'):
            args=self.inputs()
            if what=='pid':args[0]['native_pid']=124
            elif what=='cap':args[0]['max_new']=1024
            elif what=='done':args[1]['DONE_observed']=False
            elif what=='length':args[2]['finish']='length'
            elif what=='count':args[2]['generated']=3
            elif what=='reuse':args[2]['reused']=1
            elif what=='sampling':args[0]['sampling']['seed']=2
            else:args[2]['drafts_accepted']=2
            with self.subTest(what=what),self.assertRaises(ValueError):a.native_case(*args)

    def test_nonfinite_negative_or_wrong_token_path_rejected(self):
        for token,seconds in [(True,.1),(129280,.1),(3,float('nan')),(3,-1.)]:
            args=self.inputs();args[3][0]={'token':token,'seconds':seconds}
            with self.assertRaises(ValueError):a.native_case(*args)

    def test_cancel_requires_zero_native_generation_and_cancel_done(self):
        args=self.inputs();args[1]['T_lines']=0;args[2].update(generated=0,finish='cancel');args[3]=[]
        self.assertEqual(a.native_case(*args,cancelled=True)['generated'],0)
        with self.assertRaises(ValueError):a.native_case(*args)

    def test_clean_terminal_and_window_native_kernel_or_public_failures(self):
        api={'passed':True,'server_returncode':0,'grace_timeout':False,'wait_error':None,'application_stopped':True,
             'server_pid':122,'native_ready_pid':123,'native_close':[{'native_pid':123,'closed':True,'returncode':0}]}
        window={'test_returncode':0,'maintenance_resume_allowed':True,'maintenance_held':True,'maintenance_root_window':'20261025T032914Z.json'}
        kernel={'kernel_capture_returncode':0,'kernel_fault_lines':[]}
        fence={'passed':True,'children_closed':True,'same_invocation':True}
        collection={'passed':True,'unit_collected':True,'fragment_absent':True,'dropins_absent':True}
        identity={'native_sha256':'92abb8bcf6af251c9704d3f23396ea031a1d555b903ad2757a6a496ad77a71e1',
                  'config_sha256':'c43dd3d99df86cffaf071d482adb55b100288d04b86f82adddd05543e26424fa',
                  'context':1048576,'output_default':262144,'DSpark':True,'all_CPU_experts_RAM':True,'start_binding':{'native_pid':555}}
        public={'unauthenticated_models':401,'authenticated_models':200,'content':'READY','finish':'stop','SSE_done':True,'known_answer_passed':True}
        restored={'status':'S2_ESSENTIAL3_SELECTED4096_RESTORED','arm':'C0','verified':{'passed':True,'selected_identity':identity,'public':public}}
        args=[api,window,kernel,fence,collection,restored,'C0']
        self.assertTrue(a.terminal(*args)['private_native_API_window_exit0'])
        for what in ('native','window','kernel','fence','public','capacity'):
            wrong=copy.deepcopy(args)
            if what=='native':wrong[0]['native_close'][0]['returncode']=1
            elif what=='window':wrong[1]['test_returncode']=1
            elif what=='kernel':wrong[2]['kernel_fault_lines']=['fault']
            elif what=='fence':wrong[3]['children_closed']=False
            elif what=='public':wrong[5]['verified']['public']['SSE_done']=False
            else:wrong[5]['verified']['selected_identity']['context']=262144
            with self.subTest(what=what),self.assertRaises(ValueError):a.terminal(*wrong)

    def test_partial_or_failed_API_cleanup_never_accepted(self):
        for bad in [{'passed':False},{'passed':True,'server_returncode':1},
                    {'passed':True,'server_returncode':0,'grace_timeout':True}]:
            with self.assertRaises(ValueError):a.terminal(bad,{}, {}, {}, {}, {},'C0')


if __name__=='__main__':unittest.main(verbosity=2)
