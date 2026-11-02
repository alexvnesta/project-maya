#!/usr/bin/env python3
"""Bounded startup readiness for existing private SSH model endpoint; never selects/generates."""
import argparse,json,sys,time,urllib.request

def qualified(health,models):
 s=health.get('switcher') or {}
 if health.get('status')!='ok' or s.get('fault') or s.get('default_model')!='deepseek' or s.get('active_model') not in ['deepseek','qwen','glm']:return False
 if models.get('default_model')!='deepseek-v4.1-flash-iq2-xs':return False
 if s['active_model']=='deepseek' and not (health.get('loaded') and health.get('max_context')==1048576 and health.get('images') is True):return False
 return True

def main():
 p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:18012');p.add_argument('--timeout',type=float,default=1800);p.add_argument('--interval',type=float,default=5);a=p.parse_args();end=time.monotonic()+a.timeout
 while time.monotonic()<end:
  try:
   def get(path):
    with urllib.request.urlopen(a.url+path,timeout=5) as f:return json.load(f)
   h=get('/health');m=get('/v1/models')
   if qualified(h,m):print(json.dumps({'ready':True,'active':h['switcher']['active_model'],'default':'deepseek','generation_requests':0}));return
  except (OSError,ValueError,KeyError,TypeError):pass
  time.sleep(min(a.interval,max(0,end-time.monotonic())))
 raise SystemExit('Local model router did not become qualified within bounded startup wait; no app/cron started.')
if __name__=='__main__':main()
