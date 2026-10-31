"""Pure original-weight range plan and narrowly changed Maya pack metadata.

No I/O or model actions. This candidate replaces complete gate/up roles on
layers25,26 with original MXFP4. It is an independent public hybrid, not S2.
"""
import json
import posixpath
from pathlib import PurePosixPath
import re

ROWS,K,EXPERTS=2304,5120,384
WEIGHT_BYTES=ROWS*K//2
SCALE_BYTES=ROWS*K//32
MATRIX_BYTES=ROWS*K//32*17
TOTAL_BYTES=MATRIX_BYTES*EXPERTS*2*2
FILENAMES=('model-00028-of-00048.safetensors','model-00029-of-00048.safetensors')

def require(ok,why):
    if not ok:raise ValueError(why)

def pairs(items):
    d={}
    for k,v in items:
        require(k not in d,'Duplicate source header member');d[k]=v
    return d

def header(raw,file_bytes):
    require(type(raw) is bytes and 0<len(raw)<=8*2**20 and type(file_bytes) is int and file_bytes>8+len(raw),'Bounded complete source header')
    d=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite header')))
    require(type(d) is dict,'Source header mapping')
    return {'base':8+len(raw),'file_bytes':file_bytes,'tensors':d}

def plane(h,key,dtype,shape,expected_bytes):
    require(type(h['base']) is type(h['file_bytes']) is int and 0<h['base']<h['file_bytes'],'Typed source file bounds')
    d=h['tensors'][key]
    require(d['dtype']==dtype and d['shape']==shape and all(type(v) is int for v in d['shape']),'Original tensor type/shape')
    a,b=d['data_offsets'];require(type(a) is type(b) is int and 0<=a<b and b-a==expected_bytes and h['base']+b<=h['file_bytes'],'Source tensor range bounds')
    return [h['base']+a,h['base']+b]

def make_plan(index,headers):
    require(set(headers)==set(FILENAMES),'Exactly the two source headers')
    mapping=index['weight_map'];records=[];intervals={f:[] for f in FILENAMES};offset=0
    for layer in (25,26):
        for role in ('w1','w3'):
            for expert in range(EXPERTS):
                name=f'layers.{layer}.ffn.experts.{expert}.{role}.weight';scale=name[:-6]+'scale'
                fn=mapping[name];require(fn in headers and mapping[scale]==fn,'Weight/scale source shard alignment')
                w=plane(headers[fn],name,'I8',[ROWS,K//2],WEIGHT_BYTES)
                s=plane(headers[fn],scale,'F8_E8M0',[ROWS,K//32],SCALE_BYTES)
                intervals[fn].extend([tuple(w),tuple(s)])
                records.append({'name':name,'layer':layer,'expert':expert,'role':role,'source':fn,'weight_range':w,'scale_range':s,'output_offset':offset,'output_bytes':MATRIX_BYTES,'shape':[ROWS,K]})
                offset+=MATRIX_BYTES
    for ranges in intervals.values():
        ranges.sort();require(all(a[1]<=b[0] for a,b in zip(ranges,ranges[1:])),'Overlapping original source tensors')
    require(len(records)==1536 and offset==TOTAL_BYTES,'Exact complete role coverage')
    return records

def pack_metadata(ds4,tensors,records,new_model_dir,overlay_path):
    """Rebase file names to the common root; change only1536 declared expert rows."""
    require(type(ds4) is str and type(tensors) is str and len(records)==1536,'Original pack plus complete plan')
    new_model_dir=PurePosixPath(new_model_dir);overlay_path=PurePosixPath(overlay_path)
    require(new_model_dir.is_absolute() and overlay_path.is_absolute() and '..' not in new_model_dir.parts and '..' not in overlay_path.parts and overlay_path.is_relative_to(new_model_dir),'Owned overlay inside new model root')
    geometry=ds4.splitlines();old_dirs=[x[10:] for x in geometry if x.startswith('model_dir ')]
    require(len(old_dirs)==1 and PurePosixPath(old_dirs[0]).is_absolute(),'One original model directory')
    old_dir=old_dirs[0];geometry=[('model_dir '+str(new_model_dir)) if x.startswith('model_dir ') else x for x in geometry]
    by={r['name']:r for r in records};require(len(by)==1536,'Unique planned target names')
    wanted={f'layers.{l}.ffn.experts.{e}.{r}.weight' for l in (25,26) for r in ('w1','w3') for e in range(EXPERTS)}
    require(set(by)==wanted,'Only complete L25/L26 gate/up roles')
    for i,r in enumerate(records):
        require(type(r['output_offset']) is int and r['output_offset']==i*MATRIX_BYTES and type(r['output_bytes']) is int and r['output_bytes']==MATRIX_BYTES and r['shape']==[ROWS,K],'Exact contiguous output matrix geometry')
    result=[];files={};seen=set();changed=[]
    for line in tensors.splitlines():
        fields=line.split()
        require(fields,'Nonempty original tensor row')
        if fields[0]=='file':
            require(len(fields)==3 and fields[1].isdecimal(),'Original file row');i=int(fields[1]);require(i not in files,'Duplicate original file ID')
            absolute=posixpath.normpath(posixpath.join(old_dir,fields[2]));relative=posixpath.relpath(absolute,str(new_model_dir));require(not any(c.isspace() for c in relative),'File whitespace')
            require(posixpath.normpath(posixpath.join(str(new_model_dir),relative))==absolute,'Original file address preserved')
            files[i]=absolute;result.append(f'file {i} {relative}');continue
        require(fields[0]=='t' and len(fields) in (7,8),'Original tensor record')
        name=fields[1];require(name not in seen,'Duplicate original tensor name');seen.add(name)
        if name in by:
            r=by[name];require(fields[2]=='IQ2_XXS' and fields[6:]==['2304','5120'],'Only original Maya-S gate/up rows')
            require(int(fields[5])==3041280,'Original low-bit matrix size')
            result.append(f't {name} MXFP4 8 {r["output_offset"]} {r["output_bytes"]} 2304 5120');changed.append(name)
        else:result.append(line)
    require(sorted(files)==list(range(8)) and set(changed)==set(by) and len(changed)==1536,'Exact original files and target coverage')
    # All files may appear before or after tensor rows; the reader first parses the complete map.
    result.insert(8,'file 8 '+posixpath.relpath(str(overlay_path),str(new_model_dir)))
    return '\n'.join(geometry)+'\n','\n'.join(result)+'\n'
