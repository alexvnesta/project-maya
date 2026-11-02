"""Existing API server, with native shutdown receipts; no inference changes."""
import datetime,json,os,pathlib,sys
D=pathlib.Path(os.environ['MAYA_DEPLOY_ROOT'])
def observed_close(original,path):
    def close(engine):
        proc=engine.proc
        try:return original(engine)
        finally:
            if proc is not None:
                row={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'server_pid':os.getpid(),'native_pid':proc.pid,'returncode':proc.returncode,'closed':proc.poll() is not None}
                try:
                    with pathlib.Path(path).open('a') as f:f.write(json.dumps(row)+'\n');f.flush();os.fsync(f.fileno())
                except OSError:print('Native close receipt unavailable',file=sys.stderr,flush=True)
    return close
def main():
    sys.path.insert(0,str(D/'runtime-native-vision-v2'))
    from serve import server
    from hosting_defaults import install
    config=json.loads((D/"config.json").read_text())
    install(server,config["hosted_default_effort"])
    server.StrataEngine.close=observed_close(server.StrataEngine.close,D/'receipts/native-close.jsonl')
    return server.main()
if __name__=='__main__':sys.exit(main())
