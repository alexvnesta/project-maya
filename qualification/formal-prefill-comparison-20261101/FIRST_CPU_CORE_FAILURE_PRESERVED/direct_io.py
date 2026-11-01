"""Small read-only witnesses for the existing direct CPU-expert copy path."""
import os
from pathlib import Path
import re

DIRECT_FLAG=0o40000  # Linux O_DIRECT; never used to open/modify another process.

def require(ok,msg):
    if not ok:raise ValueError(msg)

def signature(p):
    s=Path(p).stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]

def counters(log):
    rows=re.findall(r'^ds4: expert copy I/O: ([0-9]+\.[0-9]{3}) GB direct, ([0-9]+\.[0-9]{3}) GB buffered fallback$',log,re.M)
    require(len(rows)==1,'Exactly one actual direct-copy counter line')
    direct,fallback=map(float,rows[0])
    require(direct>0 and fallback==0,'Actual direct bytes required, positive rendered fallback blocks this candidate')
    return {'direct_GB_rounded':direct,'buffered_fallback_GB_rounded':fallback,'rounding_GB':0.001,
            'exact_byte_count_exported':False,'exact_zero_fallback_proven':False}

def asset_paths(pack,expected_count):
    pack=Path(pack)
    dirs=[x[10:] for x in (pack/'ds4.txt').read_text().splitlines() if x.startswith('model_dir ')]
    require(len(dirs)==1 and Path(dirs[0]).is_absolute(),'One absolute source model directory')
    rows=[]
    with (pack/'tensors.txt').open() as f:
        for line in f:
            if not line.startswith('file '):break
            parts=line.rstrip('\n').split(' ',2)
            require(len(parts)==3 and parts[1]==str(len(rows)),'Contiguous source file order')
            rows.append(str((Path(dirs[0])/parts[2]).resolve(strict=True)))
    require(len(rows)==expected_count and len(set(rows))==expected_count,'Exact candidate model/drafter/vision source files')
    return rows

def rows_contract(rows,expected):
    require(type(rows) is list and len(rows)<=256 and type(expected) is dict and len(expected) in (8,9),'Bounded exact candidate source descriptor map')
    seen=set();kinds={p:set() for p in expected}
    for row in rows:
        require(set(row)=={'fd','path','flags','signature'} and type(row['fd']) is int and 0<=row['fd']<10000
                and row['fd'] not in seen and row['path'] in expected and type(row['flags']) is int
                and row['flags']>=0 and row['flags']&3==0,'Unique readonly source descriptor')
        seen.add(row['fd']);sig=row['signature']
        require(type(sig) is list and len(sig)==5 and all(type(x) is int and x>=0 for x in sig)
                and sig==expected[row['path']],'Direct and original descriptors must match the same source inode/size/times')
        kinds[row['path']].add(bool(row['flags']&DIRECT_FLAG))
    require(all(v=={False,True} for v in kinds.values()),'Each source needs original plus real O_DIRECT descriptor')
    return True

def observe(pid,pack,log,expected,*,proc=Path('/proc')):
    require(type(pid) is int and pid>1,'Actual numerical native PID')
    root=Path(proc)/str(pid);before=int((root/'stat').read_text().rsplit(') ',1)[1].split()[19])
    paths=asset_paths(pack,len(expected));require(set(paths)==set(expected),'Candidate asset set differs from closed constructor')
    require({p:signature(p) for p in paths}==expected,'Actual source differs from closed candidate asset identity');rows=[]
    entries=list((root/'fd').iterdir());require(len(entries)<=4096,'Bounded process descriptor inventory')
    for f in sorted(entries,key=lambda p:int(p.name)):
        try:target=os.readlink(f)
        except FileNotFoundError:continue
        if target not in expected:continue
        values=[x.split(':',1)[1].strip() for x in (root/'fdinfo'/f.name).read_text().splitlines() if x.startswith('flags:')]
        require(len(values)==1 and re.fullmatch('[0-7]+',values[0]) is not None,'Actual Linux fd flags')
        rows.append({'fd':int(f.name),'path':target,'flags':int(values[0],8),'signature':signature(f)})
    rows_contract(rows,expected)
    require({p:signature(p) for p in paths}==expected and int((root/'stat').read_text().rsplit(') ',1)[1].split()[19])==before,'Source/process identity drift')
    return {'native_pid':pid,'start_ticks':before,'sources':expected,'descriptors':rows,'counters':counters(log),
            'actual_linux_O_DIRECT_descriptors':True,'source_paths_not_modified':True,'model_math_equivalence_claim':False}

def saved_contract(value,log,pid,pack,start_ticks,expected):
    require(value.get('native_pid')==pid and type(pid) is int and pid>1 and type(value.get('start_ticks')) is int
            and value['start_ticks']>0 and value['start_ticks']==start_ticks and type(start_ticks) is int
            and value.get('actual_linux_O_DIRECT_descriptors') is True
            and value.get('source_paths_not_modified') is True and value.get('model_math_equivalence_claim') is False,'Exact saved native/direct-copy witness')
    require(set(asset_paths(pack,len(expected)))==set(expected) and {p:signature(p) for p in expected}==expected,'Closed candidate source identity changed')
    require(value['sources']==expected and value['counters']==counters(log),'Actual saved counters/source identity changed')
    return rows_contract(value['descriptors'],expected)
