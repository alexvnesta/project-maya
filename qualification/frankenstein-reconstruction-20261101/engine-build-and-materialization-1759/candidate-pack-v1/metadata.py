"""Pure checked reconstruction of the retained Maya-S metadata and IQ3_S overlay.

No weight reads, conversion, model loading or deployment. Tokenizer, Engram
index, vision/dense/drafter tensor rows remain byte-identical to the old pack.
"""
import hashlib
import importlib.util
import posixpath
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
Q = HERE.parent
REMOTE_Q = '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/s2-reconstruction-v1'


def require(ok, why):
    if not ok: raise ValueError(why)


def sha(data): return hashlib.sha256(data).hexdigest()


def construct(blobs, pins, plan, overlay_module):
    require(set(blobs) == set(pins) == {'ds4.txt', 'tensors.txt', 'engram.bin',
            'tokenizer/vocab.json', 'tokenizer/merges.txt', 'tokenizer/token_type.json',
            'tokenizer/tokenizer.json', 'tokenizer/chat_template.jinja'}, 'Exactly eight retained metadata outputs')
    require(all(type(b) is bytes and sha(b) == pins[n] for n, b in blobs.items()),
            'Every original metadata/tokenizer byte must match retained qualification')
    ds4, tensors = blobs['ds4.txt'].decode(), blobs['tensors.txt'].decode()
    roots = [line[10:] for line in ds4.splitlines() if line.startswith('model_dir ')]
    require(len(roots) == 1 and roots[0] ==
            '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/assets/Maya-S',
            'One exact original Maya-S asset root')
    old_root = roots[0]
    new_assets = REMOTE_Q + '/base-acquisition-v1/assets/Maya-S'
    rows, found = [], set()
    for line in tensors.splitlines():
        f = line.split()
        if f[0] != 'file': rows.append(line); continue
        require(len(f) == 3 and f[1].isdecimal(), 'Exact base file record')
        i = int(f[1]); require(i not in found and 0 <= i < 8, 'Unique exact base file table'); found.add(i)
        if i < 6:
            want = 'DeepSeek-V4.1-Flash-1017-Maya-S-IQ2_XXS-%05d-of-00006.gguf' % (i + 1)
            require(f[2] == want, 'Published main/Engram filename identity')
            rows.append(line)
        elif i == 6:
            require(f[2] == '../dspark/dspark.bin', 'Unchanged published DSpark')
            rows.append(line)
        else:
            absolute = posixpath.normpath(posixpath.join(old_root, f[2]))
            require(absolute == '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/vision-assets-1017/vision.bin',
                    'Unchanged previously qualified native vision source')
            rows.append('file 7 ' + posixpath.relpath(absolute, new_assets))
    require(found == set(range(8)), 'All unchanged base files accounted for')
    ds4 = '\n'.join('model_dir ' + new_assets if line.startswith('model_dir ') else line
                    for line in ds4.splitlines()) + '\n'
    ds4, tensors = overlay_module.pack_metadata(ds4, '\n'.join(rows) + '\n', plan,
        REMOTE_Q, REMOTE_Q + '/iq3s-bulk-v1/conversion-FIRST/overlay.iq3s')
    result = dict(blobs, **{'ds4.txt': ds4.encode(), 'tensors.txt': tensors.encode()})
    require(all(result[n] == blobs[n] for n in blobs if n not in ('ds4.txt', 'tensors.txt')),
            'No tokenizer/Engram-index rewriting')
    return result
