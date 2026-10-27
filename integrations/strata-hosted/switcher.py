"""Existing lease-preserving router, extended to explicit DeepSeek/Qwen/GLM selection."""
import asyncio
import contextlib
import json
import hashlib
import os
from pathlib import Path
import time
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from controller import Controller, TARGETS

DEEPSEEK=os.environ.get('SWITCHER_DEEPSEEK_URL','http://127.0.0.1:18141')
GLM=os.environ.get('SWITCHER_GLM_URL','http://127.0.0.1:8014')
QWEN=os.environ.get('SWITCHER_QWEN_URL','http://127.0.0.1:18420')
DEFAULT='deepseek'
CANONICAL={'deepseek':'deepseek-v4.1-flash-iq2-xs','qwen':'qwen3.8-flash-next','glm':'GLM-5.3-Flash'}
ALIASES={'deepseek':{'deepseek','deepseek-v4.1-flash','deepseek-v4.1-flash-iq2-xs'},'qwen':{'qwen','qwen3.8-flash-next','qwen3.8-flashnext','qwen3.8-flash-next-abliterated','qwen3.8-flash-next-code'},'glm':{'glm','glm-5.3-flash','glm-5.3-flash-low','glm-5.3-flash-high','glm-5.3-flash-max'}}
MAX_BODY=32*1024*1024
HOP={'host','authorization','connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade','content-length','x-dsh-default-reasoning-effort'}

def target_for(model):
    if not isinstance(model,str):raise ValueError('model must be a string')
    for target,ids in ALIASES.items():
        if model.lower() in ids:return target
    raise LookupError('model is not available')

def validate_unit_contract(text):
    fields=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    if fields.get('ActiveState')=='failed':raise RuntimeError('target model unit is failed; operator diagnosis/reset required before current model can stop')
    if fields.get('Restart')!='no' or ('/usr/bin/flock --nonblock --no-fork ' + os.environ['MAYA_QUALIFICATION_ROOT'] + '/experiment.lock ') not in fields.get('ExecStart',''):
        raise RuntimeError('effective model unit does not hold canonical lock or has automatic retry enabled')

def settled_unit_state(text):
    fields=dict(line.split('=',1) for line in text.splitlines() if '=' in line)
    state=fields.get('ActiveState')
    if state=='active':return True
    if state=='activating':return False
    raise RuntimeError('model unit failed or stopped before its startup helpers completed')

def qualified_deepseek_records(config,receipt):
    health=receipt.get('health') or {};args=config.get('args') or []
    def setting(flag):
        try:return args[args.index(flag)+1]
        except (ValueError,IndexError):return None
    if config.get('model_name')!=CANONICAL['deepseek'] or setting('--max-context')!='524288' or setting('--vision')!='on':return []
    if health.get('max_context')!=524288 or health.get('images') is not True:return []
    data=receipt.get('models',{}).get('data',[])
    return [r for r in data if r.get('id')==CANONICAL['deepseek'] and 'image' in r.get('architecture',{}).get('input_modalities',[])]

class Services:
    def __init__(self,client):
        self.client=client
        self.qwen_key=Path(os.environ.get('SWITCHER_QWEN_KEY_FILE',str(Path.home()/'.qwen-api-key'))).read_text().strip()
        if not self.qwen_key:raise RuntimeError('Qwen key file is empty')
        self.qwen_model=CANONICAL['qwen'];self.records={}
        # Capability evidence can outlive residency; loaded state remains controller-owned.
        directory=Path(os.environ['MAYA_DEPLOY_ROOT'])
        try:
            raw=(directory/'config.json').read_bytes();release=json.loads((directory/'release.json').read_text())
            if hashlib.sha256(raw).hexdigest()==release['files'][str(directory/'config.json')]:
                records=qualified_deepseek_records(json.loads(raw),json.loads((directory/'startup-ready.json').read_text()))
                if records:self.records['deepseek']=records
        except (OSError,ValueError,KeyError,TypeError):pass
    def headers(self,target):return {'Authorization':'Bearer '+self.qwen_key} if target=='qwen' else {}
    def url(self,target):return {'deepseek':DEEPSEEK,'qwen':QWEN,'glm':GLM}[target]
    def unit(self,target,action):
        return (['systemctl','--user',action,'deepseek-hosted.service'] if target=='deepseek' else
                ['systemctl','--user',action,'glm53-b2.service'] if target=='glm' else
                ['sudo','-n','systemctl',action,'qwen-flash-vllm.service'])
    async def command(self,argv,timeout=1800,allow_failure=False):
        p=await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:code=await asyncio.wait_for(p.wait(),timeout)
        except TimeoutError:
            p.kill();await p.wait();raise RuntimeError('service command timeout') from None
        if code and not allow_failure:raise RuntimeError('service command failed')
    async def active(self,target):
        argv=self.unit(target,'show')+['-p','ActiveState','--value']
        if target=='qwen':argv=argv[2:]
        p=await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        out,_=await asyncio.wait_for(p.communicate(),10)
        return p.returncode==0 and out.decode().strip() in ('active','activating','reloading','deactivating')
    async def target_preflight(self,target):
        argv=self.unit(target,'show')+['-p','ExecStart','-p','Restart','-p','ActiveState','-p','Result']
        if target=='qwen':argv=argv[2:]
        p=await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        out,_=await asyncio.wait_for(p.communicate(),10)
        if p.returncode:raise RuntimeError('effective model unit query failed')
        validate_unit_contract(out.decode())
        if target=='qwen' and not Path('/sys/class/net/docker0/bridge').is_dir():
            raise RuntimeError('Qwen Docker bridge missing; current model retained for offline diagnosis')
    async def free_gpus(self):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            async def query(fields):
                p=await asyncio.create_subprocess_exec('nvidia-smi',*fields,'--format=csv,noheader,nounits',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
                try:out,_=await asyncio.wait_for(p.communicate(),10)
                except TimeoutError:
                    p.kill();await p.wait();raise RuntimeError('GPU ownership query timed out') from None
                if p.returncode:raise RuntimeError('GPU ownership query failed')
                return out.decode().strip()
            raw=await query(['--query-gpu=memory.used']);owners=await query(['--query-compute-apps=pid'])
            try:used=[int(x) for x in raw.splitlines()]
            except ValueError:used=[]
            if len(used)==2 and max(used)<2000 and not owners:return
            await asyncio.sleep(3)
        raise RuntimeError('GPUs did not become free')
    async def maintenance(self):
        p=await asyncio.create_subprocess_exec('systemctl','--user','is-active','--quiet','strata-deepseek-window.service',stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        if await p.wait()==0:raise RuntimeError('owned GPU maintenance active; selection deferred')
    async def settle_unit(self,target):
        deadline=time.monotonic()+1500
        while time.monotonic()<deadline:
            argv=self.unit(target,'show')+['-p','ActiveState','-p','SubState']
            if target=='qwen':argv=argv[2:]
            p=await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            out,_=await asyncio.wait_for(p.communicate(),10)
            if p.returncode:raise RuntimeError('unit startup state query failed')
            if settled_unit_state(out.decode()):return
            await asyncio.sleep(2)
        raise RuntimeError('model startup helpers did not complete in time')
    async def ready(self,target):
        await self.settle_unit(target)
        deadline=time.monotonic()+1500
        while time.monotonic()<deadline:
            try:
                r=await self.client.get(self.url(target)+'/v1/models',headers=self.headers(target),timeout=5)
                h=await self.client.get(self.url(target)+'/health',headers=self.headers(target),timeout=5)
                if r.status_code==200 and h.status_code==200 and r.json().get('data'):
                    health=h.json() if h.content else {}
                    if not health.get('loaded',True) or health.get('status','ok')!='ok':
                        await asyncio.sleep(3);continue
                    if not any(str(record.get('id','')).lower() in ALIASES[target] for record in r.json()['data']):raise RuntimeError('backend model identity mismatch')
                    self.records[target]=r.json()['data']
                    if target=='qwen':self.qwen_model=r.json()['data'][0]['id']
                    return
            except (httpx.HTTPError,ValueError,KeyError):pass
            await asyncio.sleep(3)
        raise RuntimeError('backend readiness timeout')
    async def smoke(self,target):
        body={'model':self.qwen_model if target=='qwen' else CANONICAL[target],'messages':[{'role':'user','content':'Reply with exactly READY and no other final answer.'}],'reasoning_effort':'low','temperature':0,'seed':1,'max_tokens':256}
        r=await self.client.post(self.url(target)+'/v1/chat/completions',headers=self.headers(target),json=body,timeout=180)
        if r.status_code!=200:raise RuntimeError('backend real READY API failure')
        try:c=r.json()['choices'][0];ok=c['finish_reason']=='stop' and c['message']['content'].strip()=='READY'
        except (KeyError,IndexError,TypeError):ok=False
        if not ok:raise RuntimeError('backend real READY did not pass')
    async def switch(self,target):
        if target not in TARGETS:raise ValueError('unknown backend')
        await self.maintenance()
        owners=[t for t in TARGETS if await self.active(t)]
        if len(owners)>1:raise RuntimeError('multiple model units own GPUs; stop for diagnosis')
        if owners==[target]:await self.ready(target);return
        await self.target_preflight(target)
        for owner in owners:await self.command(self.unit(owner,'stop'))
        await self.free_gpus()
        await self.command(self.unit(target,'start'))
        await self.ready(target)
        await self.smoke(target)

def make_app(services=None, controller=None, http_client=None):
    state = {}

    @asynccontextmanager
    async def lifespan(app):
        client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(3600, connect=10), trust_env=False)
        backend = services or Services(client)
        ctrl = controller
        if ctrl is None:
            owners = [target for target in TARGETS if await backend.active(target)]
            if len(owners) > 1:
                await client.aclose()
                raise RuntimeError("multiple GPU owners active")
            ctrl = Controller(backend, owners[0] if owners else None,
                ttl=float(os.environ.get("SWITCHER_NONDEFAULT_IDLE_SECONDS", "900")), default=DEFAULT)
            if ctrl.active is None: await ctrl._change(DEFAULT)
            else: await backend.ready(ctrl.active)
        state.update(client=client, backend=backend, controller=ctrl)

        async def idle_return():
            while True:
                await asyncio.sleep(10)
                try:
                    await ctrl.expire()
                except Exception:
                    # No GPU retry after a failed switch; /health exposes the blocked controller.
                    pass
        timer = asyncio.create_task(idle_return())
        try:
            yield
        finally:
            timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await timer
            await client.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health():
        c, b, client = state["controller"], state["backend"], state["client"]
        def unavailable(status="unavailable"):
            # Preserve admission visibility even while the backend is loading.
            return JSONResponse({"status": status, "busy": True,
                "switcher": {"active_model": c.active, "inflight": c.inflight,
                             "waiting": c.waiters, "nondefault_idle_seconds": c.ttl, "default_model": DEFAULT, "fault": c.fault}}, status_code=503)
        if c.switching or c.active is None:
            return unavailable("switching" if c.switching else "unavailable")
        try:
            r = await client.get(b.url(c.active) + "/health", headers=b.headers(c.active), timeout=5)
            if r.status_code != 200:
                return unavailable()
            try:
                h = r.json()
            except ValueError:
                h = {}
            if not isinstance(h, dict):
                h = {}
            if h.get("status", "ok") != "ok" or (h.get("prompt_cache") or {}).get("terminal"):
                return unavailable()
            h.update(status=h.get("status", "ok"), busy=bool(h.get("busy") or c.inflight or c.waiters),
                     switcher={"active_model": c.active, "inflight": c.inflight, "waiting": c.waiters, "nondefault_idle_seconds": c.ttl, "default_model": DEFAULT, "fault": c.fault})
            return JSONResponse(h)
        except httpx.HTTPError:
            return unavailable()

    @app.get("/v1/models")
    @app.get("/models")
    async def models():
        records = getattr(state["backend"], "records", {})
        ids = [CANONICAL["deepseek"], CANONICAL["qwen"], "GLM-5.3-Flash", "GLM-5.3-Flash-low", "GLM-5.3-Flash-high", "GLM-5.3-Flash-max"]
        data = []
        for name in ids:
            target = target_for(name)
            original = next((r for r in records.get(target, []) if r["id"] == name), next(iter(records.get(target, [])), {}))
            record = {k:v for k,v in original.items() if k not in ("root", "parent")}
            record.update(id=name, object="model", owned_by="local")
            record.setdefault("created", 0)
            record["status"] = {"value": "loaded" if state["controller"].active == target else "unloaded"}
            if target == "deepseek":
                context=record.get('meta',{}).get('n_ctx')
                if isinstance(context,int):record.update(context_length=context,context_window=context,max_output_tokens=131072)
                record["capabilities"] = {"tools": True, "streaming": True, "reasoning": True,
                    "structured_output": {"formats":["json_object","json_schema"],"constrained_decoding":False},
                    "image_input": "image" in record.get("architecture",{}).get("input_modalities",["text"])}
                record["reasoning_efforts"] = ["none","low","high","max"]
                record["default_reasoning_effort"] = "max"
            data.append(record)
        return {"object":"list", "data":data, "default_model":CANONICAL[DEFAULT]}

    @app.post("/v1/switch")
    async def select(request: Request):
        try:
            body = await request.json()
            target = target_for(body.get("model", CANONICAL[DEFAULT]))
        except (ValueError, TypeError, AttributeError): return JSONResponse({"error":"invalid model selection"},status_code=400)
        except LookupError: return JSONResponse({"error":"model is not available"},status_code=404)
        try:
            async with state["controller"].lease(target):
                await state["backend"].ready(target)
                return {"active_model":target,"model":CANONICAL[target],"default_model":DEFAULT,"status":"ready"}
        except Exception: return JSONResponse({"error":"model switch stopped; inspect operator diagnostics"},status_code=503)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def forward(path, request: Request):
        allowed = {"v1/chat/completions", "v1/completions", "v1/messages", "v1/messages/count_tokens", "v1/responses", "tokenize"} if request.method == "POST" else {"metrics", "v1/status", "v1/telemetry", "props", "slots"}
        if path not in allowed:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > MAX_BODY:
                return JSONResponse({"error": "request body too large"}, status_code=413)
        c, b, client = state["controller"], state["backend"], state["client"]
        target = None  # GET /metrics observes the current owner; it never selects a model.
        payload = None
        if request.method == "POST":
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError()
                model = payload.get("model", CANONICAL[DEFAULT])
                if not isinstance(model, str):
                    raise ValueError()
                try: target = target_for(model)
                except LookupError: return JSONResponse({"error":"model is not available"}, status_code=404)
                payload.setdefault("model", CANONICAL[DEFAULT])
                default_effort=request.headers.get('x-dsh-default-reasoning-effort')
                if target=='deepseek' and path=='v1/chat/completions' and default_effort is not None:
                    if default_effort!='none':return JSONResponse({'error':'invalid Harness reasoning default'},status_code=400)
                    # Harness/pi-ai omits the effort only for its explicit Off selection.
                    # Low/high/max remain explicit and always take precedence.
                    payload.setdefault('reasoning_effort','none')
            except ValueError:
                return JSONResponse({"error": "invalid JSON request"}, status_code=400)
        async def prepare():
            lease = c.lease(target, activity=request.method == "POST")
            entered = False
            try:
                await lease.__aenter__()
                entered = True
                owner = target or c.active
                if request.method == "POST":
                    # An operator or an automatic unit restart may be loading the
                    # current owner without changing the selected model. Hold its
                    # lease and keep SSE comments flowing until it is ready.
                    # Never retry a forwarded generation: that could duplicate it.
                    await b.ready(owner)
                outgoing = bytes(body) or None
                if payload is not None:
                    obj = dict(payload)
                    if owner == "qwen":
                        obj["model"] = b.qwen_model
                    elif owner == "deepseek" or obj["model"].lower() == "glm":
                        obj["model"] = CANONICAL[owner]
                    outgoing = json.dumps(obj).encode()
                headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
                headers.pop("content-encoding", None)  # outgoing JSON was re-encoded
                headers["Accept-Encoding"] = "identity"  # SSE comments must remain plain bytes
                headers.update(b.headers(owner))
                upstream = await client.send(client.build_request(request.method, b.url(owner) + "/" + path,
                                                                   content=outgoing, headers=headers), stream=True)
                return lease, upstream
            except BaseException:
                if entered:
                    await lease.__aexit__(None, None, None)
                raise

        async def cleanup(lease, upstream):
            try:
                await upstream.aclose()
            finally:
                await lease.__aexit__(None, None, None)

        if payload is not None and payload.get("stream") is True:
            async def event_stream():
                task = asyncio.create_task(prepare())
                lease = upstream = next_chunk = None
                try:
                    # Headers and comments arrive while systemd loads the model.
                    # The public auth proxy can therefore keep Cloudflare alive.
                    while not task.done():
                        done, _ = await asyncio.wait([task], timeout=15)
                        if not done:
                            yield b": waiting for model\n\n"
                    lease, upstream = task.result()
                    if upstream.headers.get("content-encoding", "identity") != "identity":
                        raise RuntimeError("compressed event stream refused")
                    if upstream.status_code >= 400:
                        raw = await upstream.aread()
                        try:
                            error = json.loads(raw)
                        except ValueError:
                            error = {"error": {"message": "backend request failed"}}
                        yield b"data: " + json.dumps(error).encode() + b"\n\n"
                        yield b"data: [DONE]\n\n"
                        return
                    iterator = upstream.aiter_raw().__aiter__()
                    tail = b"\n\n"
                    while True:
                        next_chunk = asyncio.create_task(iterator.__anext__())
                        while not next_chunk.done():
                            done, _ = await asyncio.wait([next_chunk], timeout=15)
                            if not done and (tail.endswith(b"\n\n") or tail.endswith(b"\r\n\r\n")):
                                yield b": keepalive\n\n"
                        try:
                            chunk = next_chunk.result()
                        except StopAsyncIteration:
                            break
                        tail = (tail + chunk)[-4:]
                        yield chunk
                except Exception:
                    yield b'data: {"error":{"message":"backend unavailable or switch failed"}}\n\ndata: [DONE]\n\n'
                finally:
                    async def release():
                        if next_chunk and not next_chunk.done():
                            next_chunk.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await next_chunk
                        if lease is not None:
                            await cleanup(lease, upstream)
                        else:
                            if not task.done():
                                task.cancel()
                            try:
                                pair = await task
                            except BaseException:
                                return
                            await cleanup(*pair)
                    await asyncio.shield(asyncio.create_task(release()))
            return StreamingResponse(event_stream(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        try:
            lease, upstream = await prepare()
        except asyncio.CancelledError:
            raise
        except Exception:
            return JSONResponse({"error": "backend unavailable or switch failed"}, status_code=503)

        async def stream():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await asyncio.shield(asyncio.create_task(cleanup(lease, upstream)))
        headers = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP}
        return StreamingResponse(stream(), status_code=upstream.status_code, headers=headers)

    return app


app = make_app()
