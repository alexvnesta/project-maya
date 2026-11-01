"""Resolve all five-layer gate/up originals, without downloading weight payloads."""
import json
from pathlib import Path
import reconstruction as r


def load_inputs(directory):
    directory = Path(directory)
    index = json.loads((directory / 'official-index-FIRST.json').read_text())
    metadata = json.loads((directory / 'official-HF-metadata-FIRST.json').read_text())
    r.require(metadata['sha'] == r.OFFICIAL_REVISION, 'Original checkpoint revision')
    siblings = {f['rfilename']: f for f in metadata['siblings']}
    headers = {}
    for i in range(27, 32):
        name = f'model-{i:05d}-of-00048.safetensors'
        d = json.loads((directory / ('header-' + name + '.json')).read_text())
        r.require(d['source_revision'] == r.OFFICIAL_REVISION and d['source_file'] == name
                  and d['source_file_sha256'] == siblings[name]['lfs']['sha256']
                  and d['file_bytes'] == siblings[name]['size'], 'Header/checkpoint file identity')
        headers[name] = d
    return index, headers


def make(index, headers):
    records, intervals = [], {name: [] for name in headers}
    for layer in r.SENSITIVE:
        for expert in range(r.EXPERTS):
            # One complete native expert's source identities; gate/up only for this overlay.
            for native in r.native_records({'selected': [[layer, expert]], 'count': 1})[:2]:
                ranges = r.original_range(native, index, headers)
                for plane in ranges.values():
                    intervals[plane['file']].append((plane['offset'], plane['offset'] + plane['bytes']))
                target = len(records) * r.matrix_bytes(native['role'], 'IQ3_S')
                records.append({'layer': layer, 'expert': expert, 'role': native['role'],
                                'shape': native['shape'], 'source_ranges': ranges,
                                'target_dtype': 'IQ3_S', 'target_offset': target,
                                'target_bytes': r.matrix_bytes(native['role'], 'IQ3_S')})
    for values in intervals.values():
        ordered = sorted(values)
        r.require(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), 'No overlapping source planes')
    r.require(len(records) == 3840, 'Complete L24-28 gate/up coverage')
    return {'scope': 'Source ranges and byte budget only; no weights encoded or inference executed',
            'official_revision': r.OFFICIAL_REVISION, 'matrix_count': len(records),
            'source_native_mxfp4_bytes': sum(p['bytes'] for d in records for p in d['source_ranges'].values()),
            'target_iq3_s_bytes': sum(d['target_bytes'] for d in records),
            'source_full_shards_bytes': sum(h['file_bytes'] for h in headers.values()),
            'CPU_1870_expert_ids': 'UNFROZEN', 'encoder_calibration_qualified': False,
            'records': records}
