"""Candidate-specific small metadata and cooperative immutable asset custody.

Initial full payload digests belong to the completed download/constructor
receipts. Runtime guards compare the exact recorded stat identities, and do
not rehash model payloads or claim independent fresh tensor attestation.
"""
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import engine_profile as profile

P=Path(__file__).resolve().parent
E=P.parents[1]
DATA=E/'decode-optimization-20261028/model-choice-v1'
TOKENIZER_NAMES={'vocab.json','merges.txt','token_type.json','tokenizer.json','chat_template.jinja'}

def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def pin(q,path):
    require(q['files'].get(str(path))==sha(path),'Exact candidate metadata/proof omitted or changed')

def contract(doc):
    require(doc.get('read_only_metadata_reconciliation') is True and doc.get('new_full_tensor_hashes_computed') is False
        and doc.get('no_model_admission') is True and set(doc['candidates'])=={'HGU','UNSLOTH'},'Exact two-pack custody scope')
    for name,row in doc['candidates'].items():
        f=profile.factor(name);relative=Path(row['pack_relative_to_E'])
        require(not relative.is_absolute() and '..' not in relative.parts and str(profile.E/relative)==f['pack'], 'Exact candidate pack')
        require(row.get('constructor_success') is True and row.get('exact_private_S2') is False
            and row.get('runtime_fit_or_numeric_quality_speed_proof') is False,'Constructor evidence is not runtime/quality evidence')
        require(set(row['metadata_sha256'])=={'ds4.txt','tensors.txt','engram.bin'}
            and set(row['tokenizer_sha256'])==TOKENIZER_NAMES,'Complete candidate metadata/tokenizer inventory')
        require(len(row['assets'])==f['asset_count'] and [v['file'] for v in row['assets']]==list(range(f['asset_count']))
            and all(type(v['file']) is int for v in row['assets']),'Exact contiguous candidate assets')
        paths=[]
        for asset in row['assets']:
            path=Path(asset['path']);sig=asset['signature']
            require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(profile.E)
                and type(sig) is list and len(sig)==5 and all(type(x) is int and x>0 for x in sig),'Typed canonical asset identity')
            paths.append(str(path))
        require(len(set(paths))==len(paths) and set(row['proof_relative_to_E'])==set(row['proof_sha256'])
            and all(re.fullmatch('[0-9a-f]{64}',v) for v in [*row['proof_sha256'].values(),*row['metadata_sha256'].values(),*row['tokenizer_sha256'].values()]),'Unique assets/exact proof hashes')
        for relative in row['proof_relative_to_E']:
            path=Path(relative);require(not path.is_absolute() and '..' not in path.parts,'Canonical proof inventory')
        if name=='HGU':
            closure=row['overlay_closure']
            require(row['changed_matrices']==1536 and row['unchanged_tensors']==47259 and row['assets'][8]['signature'][2]==9625927680
                and closure['constructor_sha256_record']=='e386661b7ca9faf94188d8a9cb899e39faf9b54c8b85ad81639e18c993a17b1a'
                and closure['mtime_ctime_both_before_finished_UTC'] is True and closure['new_full_hash_computed'] is False,'Completed original-GU overlay continuity')
    return True

def dossier():
    doc=read(DATA/'PACK_CUSTODY_FROZEN.json');contract(doc);return doc

def assets(variant):
    profile.factor(variant)
    return {v['path']:v['signature'][:] for v in dossier()['candidates'][variant]['assets']}

def actual_signature(path):
    p=Path(path);require(p.resolve()==p and not p.is_symlink() and p.is_file(),'Canonical actual source asset')
    s=p.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def closed_contract(name,row,closed,*,original=None,child=None,download=None,ledger=None):
    """Reconcile saved completed constructor facts; never execute a codec/model."""
    outputs={**row['metadata_sha256'],**{'tokenizer/'+k:v for k,v in row['tokenizer_sha256'].items()}}
    if name=='HGU':
        require(closed.get('status')=='PUBLIC_NATIVE_GU_PACK_CONSTRUCTED_NOT_MODEL_QUALIFIED'
            and type(closed.get('returncode')) is int and closed['returncode']==0
            and closed.get('exact_private_S2') is False and closed.get('model_GPU_service_actions')==0
            and closed['pack_files']==outputs and closed['overlay']['bytes']==9625927680
            and closed['overlay']['matrices']==1536 and closed['overlay']['sha256']==row['overlay_closure']['constructor_sha256_record'], 'Closed original-GU constructor/status/metadata/full-overlay digest')
        require(original.get('status')=='PACK_METADATA_VERIFIED_NO_MODEL_ADMISSION'
            and type(child.get('returncode')) is int and child['returncode']==0 and child.get('error') is None
            and child.get('cleanup_errors')==[] and child.get('CPU_limit_seconds')==30
            and child.get('Linux_AS_bytes')==512*2**20 and child.get('wall_limit_seconds')==90
            and child.get('nice_increment')==15,'Completed original Maya-S metadata constructor closure')
        before={**original['asset_stats'],**original['vision_stats']}
        require(all(before.get(a['path'])==a['signature'] for a in row['assets'][:8]), 'Original eight source signatures changed')
        finish=datetime.datetime.fromisoformat(closed['finished_utc'])
        require(finish.utcoffset()==datetime.timedelta(0) and max(row['assets'][8]['signature'][3:])<=int(finish.timestamp()*1e9), 'Overlay changed after constructor final hash closure')
        require(type(ledger) is list and len(ledger)==1536,'Complete1536 matrix ledger')
        expected={'layers.%d.ffn.experts.%d.%s.weight'%(l,e,r) for l in (25,26) for e in range(384) for r in ('w1','w3')}
        seen=set();pids=set();offset=0
        for matrix in ledger:
            codec=matrix['codec'];label=matrix['name']
            require(label in expected and label not in seen and type(matrix['output_offset']) is int and matrix['output_offset']==offset
                and type(matrix['output_bytes']) is int and matrix['output_bytes']==6266880 and type(codec.get('returncode')) is int and codec['returncode']==0
                and type(codec['pid']) is int and codec['pid']>1 and codec['pid'] not in pids
                and 0<codec['elapsed_seconds']<90 and re.fullmatch('[0-9a-f]{64}',codec['output_sha256']), 'Matrix coverage/offset/actual codec exit/digest')
            require(codec['configured_bounds']['CPU']==30 and codec['configured_bounds']['AS_linux']==512*2**20
                and codec['configured_bounds']['wall']==90 and codec['configured_bounds']['nice']==15
                and codec['configured_bounds']['environment']['CUDA_VISIBLE_DEVICES']=='', 'Saved codec configured envelope')
            seen.add(label);pids.add(codec['pid']);offset+=matrix['output_bytes']
        require(seen==expected and offset==9625927680,'Complete exact original-GU overlay range')
    else:
        require(name=='UNSLOTH' and closed.get('status')=='UNSLOTH_PACK_METADATA_CONSTRUCTED_NOT_MODEL_QUALIFIED'
            and type(closed.get('returncode')) is int and closed['returncode']==0 and closed['pack_sha256']==outputs
            and closed.get('all_incoming_tokenizer_payloads_preserved') is True and closed.get('model_native_GPU_build_service_actions')==0,'Completed Unsloth constructor and preserved tokenizer')
        bounds=closed['actual_bounds']
        require(bounds['cpu']==[30,30] and bounds['as']==[512*2**20]*2 and bounds['nice']==15
            and bounds['environment']['CUDA_VISIBLE_DEVICES']=='','Actual Unsloth metadata child limits')
        before={**closed['source_asset_stats'],**closed['supplement_stats']}
        require(all(before.get(a['path'])==a['signature'] for a in row['assets']), 'Original Unsloth/drafter/vision signatures changed')
        require(download.get('status')=='ALL_SIX_UNSLOTH_ASSETS_VERIFIED_NO_MODEL_RUN'
            and type(download.get('returncode')) is int and download['returncode']==0 and len(download['files'])==6
            and all(x['status'] in ('VERIFIED_EXISTING','DOWNLOADED_VERIFIED') and type(x['bytes']) is int and x['bytes']>0
                    and re.fullmatch('[0-9a-f]{64}',x['sha256']) for x in download['files']), 'All six original full-SHA acquisition closures')
    return True

def guard(q,*,stat_reader=actual_signature):
    path=DATA/'PACK_CUSTODY_FROZEN.json';pin(q,path);doc=dossier()
    att=DATA/'ASSET_STAT_ATTESTATION_FIRST.json';pin(q,att)
    require(sha(att)==doc['attestation_sha256'],'Actual initial asset witness differs')
    initial=read(att)
    for name,row in doc['candidates'].items():
        require(initial['candidates'][name]['assets']==row['assets'],'Closed constructor/fresh stat reconciliation differs')
        for relative,digest in row['proof_sha256'].items():
            f=E/relative;pin(q,f);require(sha(f)==digest,'Completed constructor proof changed')
        pack=E/row['pack_relative_to_E']
        for root,pins in [(pack,row['metadata_sha256']),(pack/'tokenizer',row['tokenizer_sha256'])]:
            for n,digest in pins.items():
                f=root/n;pin(q,f);require(sha(f)==digest,'Completed candidate pack metadata/template changed')
        base=E/'decode-optimization-20261028'
        if name=='HGU':
            source=base/'s2-public-hybrid-v1/native-gu-FIRST';old=base/'maya-s-comparison-v1/pack-v3/construct-CPU-FIRST'
            for f in (source/'state.json',source/'matrices.jsonl',old/'pack-result.json',old/'child.json'):
                relative=str(f.relative_to(E));require(relative in row['proof_sha256'],'Mandatory actual constructor closure omitted');pin(q,f)
            ledger=[json.loads(x) for x in (source/'matrices.jsonl').read_text().splitlines()]
            closed_contract(name,row,read(source/'state.json'),original=read(old/'pack-result.json'),child=read(old/'child.json'),ledger=ledger)
        else:
            for f in (base/'unsloth-pack-v1/CONSTRUCTION_RESULT_R2_FIRST.json',base/'unsloth-v31-iq2xxs-download-v1/STATE64.json'):
                relative=str(f.relative_to(E));require(relative in row['proof_sha256'],'Mandatory actual Unsloth closure omitted');pin(q,f)
            closed_contract(name,row,read(base/'unsloth-pack-v1/CONSTRUCTION_RESULT_R2_FIRST.json'),download=read(base/'unsloth-v31-iq2xxs-download-v1/STATE64.json'))
        for path,signature in assets(name).items():require(stat_reader(path)==signature,'Candidate tensor identity changed since completed constructor')
    return True



