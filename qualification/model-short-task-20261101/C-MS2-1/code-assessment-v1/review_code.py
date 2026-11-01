"""Bounded checks of a module manually inspected and pinned before execution."""
import argparse,ast,copy,hashlib,io,json,pathlib,platform,random,resource,signal,types,unittest
p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--manual-note',required=True);a=p.parse_args()
source=a.source.read_text();assert hashlib.sha256(source.encode()).hexdigest()==a.sha256
assert a.manual_note.strip()
tree=ast.parse(source)
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
main_functions=[n for n in functions if n.name=='coalesce_ranges']
assert len(main_functions)==1 and not main_functions[0].decorator_list
fn=main_functions[0];helpers=[n for n in functions if n is not fn]
assert len(helpers)<=1
def reviewed_helper(node):
 expected=ast.parse('def _require_integer_endpoint(value):\n    if isinstance(value, bool) or not isinstance(value, int):\n        raise TypeError("range endpoints must be integers and not bool")\n').body[0]
 return ast.dump(node)==ast.dump(expected)
if helpers:
 assert reviewed_helper(helpers[0]), 'Unreviewed helper implementation'

def reviewed_import_from(node):
 return node.module in {'__future__','typing'} or ast.dump(node)==ast.dump(ast.parse('from copy import deepcopy').body[0])
def reviewed_sort_key(node):
 return ast.dump(node)==ast.dump(ast.parse('lambda interval: interval[0]',mode='eval').body)

for n in tree.body:
 assert isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef,ast.If,ast.Expr))
 if isinstance(n,ast.Import):assert all(x.name in {'unittest','copy'}for x in n.names)
 if isinstance(n,ast.ImportFrom):assert reviewed_import_from(n)
for n in ast.walk(tree):
 if isinstance(n,ast.Name):assert n.id not in {'eval','exec','compile','open','__import__','globals','locals','getattr','setattr','delattr','input','breakpoint'}
 if isinstance(n,ast.Attribute):assert not n.attr.startswith('__')
for n in ast.walk(fn):
 if isinstance(n,ast.Lambda):assert reviewed_sort_key(n), 'Unreviewed sort-key lambda'
 assert not isinstance(n,(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal,ast.With,ast.AsyncFunctionDef,ast.Await))
 if isinstance(n,ast.Call):
  if isinstance(n.func,ast.Name):assert n.func.id in {'isinstance','len','list','tuple','sorted','max','min','enumerate','iter','TypeError','ValueError'}|({'_require_integer_endpoint'}if helpers else set())
  else:assert isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.attr in {'append','sort','copy'}
resource.setrlimit(resource.RLIMIT_CPU,(3,3));limit=None
if platform.system()=='Linux':resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20));limit=512
signal.alarm(5)
ns={'__builtins__':{k:__builtins__.__dict__[k] for k in ['isinstance','len','list','tuple','sorted','max','min','enumerate','iter','bool','int','TypeError','ValueError']}}
exec(compile(ast.Module(body=helpers+[fn],type_ignores=[]),'manually-reviewed-coalesce','exec'),ns);function=ns['coalesce_ranges']
def reference(rows):
 events={}
 for start,end in rows:
  if isinstance(start,bool)or isinstance(end,bool)or not isinstance(start,int)or not isinstance(end,int):raise TypeError()
  if start>end:raise ValueError()
  if start==end:continue
  events[start]=events.get(start,0)+1;events[end]=events.get(end,0)-1
 active=0;opened=None;answer=[]
 for x in sorted(events):
  before=active;active+=events[x]
  if before==0 and active>0:opened=x
  elif before>0 and active==0:answer.append((opened,x))
 return answer
rng=random.Random(20261025)
cases=[[],[(0,0)],[(2,2),(0,1),(1,2)],[(5,8),(0,4),(4,6)],[(0,10),(2,3)],[[3,5],[1,4],[7,8],[6,6]],[(0,1),(0,1)],[(10**200,10**200+5),(-10**200,0),(0,10**200)]]
for i in range(2048):
 rows=[]
 for j in range(rng.randrange(26)):
  x,y=rng.randint(-100,100),rng.randint(-100,100);rows.append([min(x,y),max(x,y)] if i%2 else(min(x,y),max(x,y)))
 cases.append(rows)
for i in range(128):
 scale=10**rng.randrange(20,200);cases.append([(scale-7,scale),(-scale,0),(0,scale-9),(scale,scale)])
for bad in [True,False,1.,'1',None,[],{},(),b'1',complex(1,0)]:cases.extend([[(0,1),(bad,2)],[(0,1),(0,bad)]])
cases.extend([[(0,1),(3,2)],[[0,1],[-1,-2]],[(2,2),(7,6)]])
def evaluate(f):
 errors=[];checks=0
 for i,rows in enumerate(cases):
  original=copy.deepcopy(rows);given=copy.deepcopy(rows);expected=None;expected_error=None;value=None;observed_error=None
  try:expected=reference(original)
  except(TypeError,ValueError)as e:expected_error=type(e)
  try:value=f(given)
  except Exception as e:observed_error=type(e)
  checks+=1
  if observed_error!=expected_error or(expected_error is None and(value!=expected or type(value)is not list or any(type(x)is not tuple for x in value))):errors.append({'case':i,'category':'reference_or_type','expected_error':getattr(expected_error,'__name__',None),'actual_error':getattr(observed_error,'__name__',None)})
  checks+=1
  if given!=original:errors.append({'case':i,'category':'input_mutation'})
 return {'cases':len(cases),'checks':checks,'errors':errors,'passed':not errors}
independent=evaluate(function)
module=types.ModuleType('manually_reviewed_synthetic_module');exec(compile(tree,'reviewed-synthetic-module','exec'),module.__dict__)
stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
(a.source.parent/('supplied-tests-'+platform.system().lower()+'.log')).write_text(stream.getvalue())
def no_touch(rows):
 reference(rows);out=[]
 for x,y in sorted((x,y)for x,y in rows if x!=y):
  if not out or x>=out[-1][1]:out.append((x,y))
  else:out[-1]=(out[-1][0],max(out[-1][1],y))
 return out
def mutating(rows):rows.sort();return reference(rows)
def bool_accept(rows):return reference([(int(x)if isinstance(x,bool)else x,int(y)if isinstance(y,bool)else y)for x,y in rows])
def keep_empty(rows):return reference(rows)+[(x,y)for x,y in rows if x==y]
negative={name:not evaluate(f)['passed']for name,f in [('no_touch_merge',no_touch),('mutates_input',mutating),('accepts_bool',bool_accept),('keeps_empty',keep_empty)]}
report={'platform':platform.system(),'source_sha256':a.sha256,'manual_review':a.manual_note,'reviewer_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'independent':independent,'supplied_tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful()},'negative_controls_rejected':negative,'CPU_limit_seconds':3,'address_space_limit_MiB':limit,'scope':'One new frozen C-MS2-1 Maya145/MayaS TP2 coding output; no broad quality or comparative speed claim.'}
(a.source.parent/('code-review-'+platform.system().lower()+'.json')).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));assert independent['passed']and result.wasSuccessful()and all(negative.values())
