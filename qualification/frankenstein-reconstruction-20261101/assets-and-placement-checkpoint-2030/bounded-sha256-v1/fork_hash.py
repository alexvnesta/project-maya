"""Exact SHA256 with bounded CPU work per inherited single-thread CPU process.

Each hop updates an inherited hashlib context over <=4GiB and forks the next
hop. No digest-state serialization, Merkle substitution, limit extension or
GPU context. All descendants remain in the original owned process group; each
parent waits for its direct child and propagates its actual result. Use only
inside the existing CPU30/AS512/wall90 data-child supervisor.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import stat
import sys
import threading

MAX_HOP=4*2**30
MAX_HOPS=64


def require(ok,why):
    if not ok:raise ValueError(why)


def stamp(s):return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def observed():
    return {'pid':os.getpid(),'ppid':os.getppid(),'pgid':os.getpgrp(),'cpu':list(resource.getrlimit(resource.RLIMIT_CPU)),
        'as':list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform=='linux' else None,
        'nice':os.getpriority(os.PRIO_PROCESS,0),'isolated':bool(sys.flags.isolated),
        'dont_write_bytecode':sys.dont_write_bytecode,'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES')}


def bounds(row):
    require(row['cpu']==[30,30] and row['nice']==15 and row['isolated'] is True and
        row['dont_write_bytecode'] is True and row['CUDA_VISIBLE_DEVICES']=='' and
        row['as']==([512*2**20]*2 if sys.platform=='linux' else None),'Existing bounded CPU child only')


def encode(row):return json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def write_all(fd,data):
    while data:
        n=os.write(fd,data);require(n>0,'Child result pipe write');data=data[n:]


def hop(fd,identity,h,offset,chunk,group):
    obs=observed();bounds(obs);require(obs['pgid']==group and threading.active_count()==1,'Single-thread same owned CPU group')
    require(stamp(os.fstat(fd))==identity,'Stable original file at hop entry')
    end=min(identity[2],offset+chunk);start=offset
    while offset<end:
        data=os.pread(fd,min(2**20,end-offset),offset);require(bool(data),'Complete exact source bytes')
        h.update(data);offset+=len(data)
    require(stamp(os.fstat(fd))==identity,'Stable original file at hop completion')
    usage=resource.getrusage(resource.RUSAGE_SELF)
    own={'observed':obs,'offset':start,'end':end,'own_user_seconds':usage.ru_utime,'own_system_seconds':usage.ru_stime}
    require(all(math.isfinite(own[k]) and own[k]>=0 for k in ('own_user_seconds','own_system_seconds')),'Actual finite self CPU usage')
    if offset==identity[2]:return {'sha256':h.hexdigest(),'bytes':identity[2],'fingerprint':identity,'hops':[own]}
    readfd,writefd=os.pipe();pid=os.fork()
    if pid==0:
        os.close(readfd)
        try:
            result=hop(fd,identity,h,offset,chunk,group)
            write_all(writefd,encode({'passed':True,'result':result}));os.close(writefd);os._exit(0)
        except BaseException as exc:
            try:write_all(writefd,encode({'passed':False,'error':repr(exc)}))
            finally:os.close(writefd);os._exit(1)
    os.close(writefd);raw=b''
    try:
        while True:
            block=os.read(readfd,65536)
            if not block:break
            raw+=block;require(len(raw)<=256*1024,'Bounded descendant receipt')
    finally:os.close(readfd)
    waited,status,child_usage=os.wait4(pid,0)
    require(waited==pid and os.waitstatus_to_exitcode(status)==0,'Actual descendant wait0, no retry')
    payload=json.loads(raw);require(payload.get('passed') is True,'Complete descendant hash result')
    result=payload['result'];require(result['hops'][0]['observed']['pid']==pid and
        result['hops'][0]['observed']['ppid']==obs['pid'] and result['hops'][0]['offset']==end and
        result['fingerprint']==identity,'Exact next inherited context/owned PID/offset')
    own['waited_child_pid']=pid;own['waited_child_returncode']=0
    own['wait4_includes_descendants_user_seconds']=child_usage.ru_utime
    own['wait4_includes_descendants_system_seconds']=child_usage.ru_stime
    result['hops'].insert(0,own);return result


def file_sha256(path,*,hop_bytes=MAX_HOP):
    require(type(hop_bytes) is int and 0<hop_bytes<=MAX_HOP,'Bounded hash hop size')
    path=Path(path);require(path.is_absolute() and path.resolve()==path and not path.is_symlink(),'Real explicit source file')
    s=path.stat();identity=stamp(s)
    require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and (s.st_size+hop_bytes-1)//hop_bytes<=MAX_HOPS,'One stable ordinary bounded-hop file')
    bounds(observed());require(threading.active_count()==1,'No fork from multithreaded process')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        require(stamp(os.fstat(fd))==identity,'Exact opened inode')
        result=hop(fd,identity,hashlib.sha256(),0,hop_bytes,os.getpgrp())
        require(stamp(os.fstat(fd))==stamp(path.stat())==identity,'Source stable through whole hash')
    finally:os.close(fd)
    require(result['bytes']==identity[2] and result['hops'][0]['offset']==0 and result['hops'][-1]['end']==identity[2] and
        all(left['end']==right['offset'] for left,right in zip(result['hops'],result['hops'][1:])),'Complete contiguous original-order SHA256')
    return result
