"""Reconcile only the independently accepted v4 prefix, without regrading v4."""
import hashlib
import json
from pathlib import Path

REMOTE = Path('/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1')
PRIOR_Q = '572938dfef80ef6f38d521116ed2d6288f91a969354e233888c02ba83c7871d3'
ROOT_REVIEW = '91116fb7b38479e47dd9b4b597f855783e65d281b98268a271cf4c6560c486fd'
ASTRA_REVIEW = '5457ce965c29754959b25791db2e36983001fb2f618d2db7cdd36989117c95bc'
DISPATCH_KEYS = ('DS4_IQ_OWN', 'DS4_IQ_AVX2', 'DS4_IQ_GATHER', 'DS4_IQ_VERBOSE',
                 'STRATA_NO_IQ256', 'STRATA_NO_IQ512', 'STRATA_NO_IQ4NL',
                 'STRATA_GLM_CPU_MT', 'STRATA_GLM_CPU_1T')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def typed_equal(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def check(b, q, parser, prior, full_jobs):
    def file(relative, pin=None):
        rel = Path(relative)
        require(not rel.is_absolute() and '..' not in rel.parts, 'Foreign prior evidence path')
        path = prior / rel
        actual = hashlib.sha256(b.regular(path).read_bytes()).hexdigest()
        require(q['files'].get(str(REMOTE / 'numerical-v4' / rel)) == actual
                and (pin is None or pin == actual), 'Prior evidence digest or membership differs')
        return path

    old = json.loads(file('qualification.json', PRIOR_Q).read_text())
    require(all(q['files'].get(k) == v for k, v in old['files'].items()), 'Prior qualification file omitted')
    require(old['fixture_sha256'] == q['fixture_sha256']
            and old['source_sha256']['output_parser.py'] == q['source_sha256']['output_parser.py']
            and old['CPU_capability_receipt_sha256'] == q['CPU_capability_receipt_sha256']
            and old['selected_native_sha256'] == q['selected_native_sha256'], 'Prior arithmetic identity differs')
    require(typed_equal(old['jobs'], full_jobs) and len(full_jobs) == 46
            and typed_equal(q['jobs'], full_jobs[25:]), 'Exact disjoint remaining suffix required')
    for name, pin in [('PARTIAL_ROOT_REVIEW.json', ROOT_REVIEW), ('PARTIAL_ASTRA_REVIEW.json', ASTRA_REVIEW)]:
        review = json.loads(file(name, pin).read_text())
        require(review.get('raw_sha256'), 'Prior raw review map empty')
        for rel, digest in review['raw_sha256'].items(): file(rel, digest)
    partial = json.loads(file('numerical-FIRST/partial.json').read_text())
    supervisor = json.loads(file('numerical-supervision-FIRST/result.json').read_text())
    require(supervisor['status'] == 'DEFERRED_BUSY_PARTIALS_RETAINED'
            and supervisor['error'] == "ValueError('DEFERRED_BUSY_UNTOUCHED_OR_CLEANUP_OWNED_COMPILER')"
            and supervisor['error_notes'] == [] and supervisor['own_claim_released'] is True
            and supervisor['owned_groups_absence']['passed'] is True,
            'Clean ordinary busy deferral required')
    accepted = partial['completed']
    require(len(accepted) == 25 and typed_equal([x['job'] for x in accepted], full_jobs[:25])
            and typed_equal(partial['unrun'], full_jobs[25:]), 'Prior accepted prefix or remaining suffix differs')
    children = supervisor['owned_groups_absence']['children']
    require(len(children) == 26 and [x['name'] for x in children] == [x['id'] for x in full_jobs[:26]]
            and all(x['returncode'] == 0 and x['group_absent'] is True for x in children),
            'Prior attempted child inventory differs')
    cases = 0
    for index, row in enumerate(accepted):
        name = 'numerical-FIRST/' + row['job']['id'] + '/'
        child = json.loads(file(name + 'child.json', row['child_sha256']).read_text())
        result = json.loads(file(name + 'result.json', row['result_sha256']).read_text())
        observed = json.loads(file(name + 'observed.json', row['observed_sha256']).read_text())
        dispatch = json.loads(file(name + 'dispatch-environment.json', row['dispatch_sha256']).read_text())
        pid = row['pid']
        require(type(pid) is int and pid == child['pid'] == observed['pid'] == observed['pgid']
                == dispatch['pid'] == dispatch['pgid'] == children[index]['pid']
                and observed['ppid'] == supervisor['record']['controller_pid'], 'Prior child identity differs')
        require(child['status'] == 'PASS' and child['returncode'] == 0 and child['error'] is None
                and child['cleanup'] == [] and child['error_notes'] == []
                and child['fixture_sha256'] == q['fixture_sha256']
                and observed['cpu'] == [30, 30] and observed['as'] == [512 * 2**20] * 2
                and observed['nice'] == 15 and dispatch['stage'] == 'PREEXEC_PYTHON',
                'Prior accepted child resource/exit differs')
        environment = {**b.ENV, 'TMPDIR': str(REMOTE / 'numerical-v4' / name / 'tmp')}
        require(observed['environment'] == environment, 'Prior controlled environment differs')
        require(dispatch['dispatch'] == {k: ('1' if k == 'STRATA_NO_IQ256'
                and row['job']['mode'] == 'fallback' else None) for k in DISPATCH_KEYS},
                'Prior dispatch overrides differ')
        argv = [str(REMOTE / 'fixture-repair-v4/build-FIRST/iq2xs_exact'),
                '--n', str(row['job']['n']), '--expect', row['job']['mode']]
        if row['job']['pair'] is not None:
            argv += ['--pair', ':'.join(map(str, row['job']['pair']))]
        require(child['argv'] == argv, 'Prior exact fixture argv differs')
        stdout, stderr = file(name + 'stdout'), file(name + 'stderr')
        for key, path in [('stdout', stdout), ('stderr', stderr)]:
            require(child['output_sha256'][key] == hashlib.sha256(path.read_bytes()).hexdigest(),
                    'Prior numerical output digest differs')
        require(parser.parse(stdout.read_bytes(), stderr.read_bytes(), row['job']) == result
                and row['cases'] == result['cases'], 'Prior strict parsed finite rows differ')
        cases += result['cases']
    # The last old child remains unaccepted even though its executable returned0.
    last = 'numerical-FIRST/' + full_jobs[25]['id'] + '/'
    child = json.loads(file(last + 'child.json').read_text())
    require(child['status'] == 'HOLD' and child['returncode'] == 0
            and not (prior / last / 'result.json').exists(), 'Old unaccepted child was regraded')
    require(cases == 4824 and len(q['jobs']) == 21, 'Prior finite coverage count differs')
    return {'prior_accepted_jobs': 25, 'prior_case_rows': cases,
            'new_required_jobs': 21, 'new_required_case_rows': 1512,
            'combined_required_jobs': 46, 'combined_required_case_rows': 6336,
            'old_v4_complete': False, 'old_unaccepted_child_regraded': False}
