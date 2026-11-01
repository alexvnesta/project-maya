"""Capture actual outer controller exit across SSH disconnect; no retry or GPU work.

The target retains all admission, resource, window and cleanup deadlines. This
lightweight parent never kills/restarts/adopts a target or extends its deadline.
It only writes an exclusive launch and actual wait() result for its own child.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
Q=HERE.parent


def require(ok,why):
    if not ok:raise ValueError(why)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def emit(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())


def capture(command,folder,*,cwd=None):
    folder=Path(folder);require(folder.parent.resolve()==folder.parent and not folder.exists() and not folder.is_symlink(),'Fresh captured launch namespace')
    require(type(command) is list and command and all(type(x) is str and x for x in command),'Explicit argv only')
    folder.mkdir();proc=None;began=time.monotonic();error=None;rc=None
    try:
        with (folder/'stdout.log').open('xb') as out,(folder/'stderr.log').open('xb') as err:
            proc=subprocess.Popen(command,cwd=cwd,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
            emit(folder/'controller-start.json',{'pid':proc.pid,'supervisor_pid':os.getpid(),'argv':command,'cwd':str(cwd) if cwd else None})
            rc=proc.wait()
    except BaseException as exc:
        error=repr(exc)
        # No action against an unknown/foreign group. The target controller owns
        # its complete deadline and restoration even if this observer fails.
        raise
    finally:
        emit(folder/'controller-exit.json',{'pid':proc.pid if proc else None,'supervisor_pid':os.getpid(),
            'argv':command,'returncode':rc,'error':error,'cleanup':[], 'elapsed_seconds':time.monotonic()-began,
            'actual_wait_observed':rc is not None,'retry':False,'target_signals_sent':0})
    return rc


def checked(plan_path,pin):
    plan_path=Path(plan_path);require(plan_path.resolve()==plan_path and plan_path.is_relative_to(Q) and
        not plan_path.is_symlink() and sha(plan_path)==pin,'Exact explicit root-reviewed launch plan')
    plan=json.loads(plan_path.read_text())
    require(plan['ROOT_explicit_admission'] is True and plan['no_replay'] is True and plan['target_owns_bounds_and_restore'] is True,
        'Separate actual target admission remains mandatory')
    argv=plan['argv'];require(type(argv) is list and len(argv)>=4 and argv[1:3]==['-I','-B'],'Isolated exact Python target')
    script=Path(argv[3]);require(script.resolve()==script and script.is_relative_to(Q) and not script.is_symlink() and
        sha(script)==plan['target_source_sha256'] and Path(argv[0]).is_absolute(),'Actual admitted target source')
    require(Path(plan['cwd'])==script.parent and Path(plan['output']).parent==HERE,'Owned fresh output and actual cwd')
    return plan


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True);parser.add_argument('--sha256',required=True);a=parser.parse_args()
    plan=checked(a.plan,a.sha256)
    rc=capture(plan['argv'],plan['output'],cwd=plan['cwd'])
    require(checked(a.plan,a.sha256)==plan,'Launch plan/source changed during captured target')
    return rc


if __name__=='__main__':raise SystemExit(main())
