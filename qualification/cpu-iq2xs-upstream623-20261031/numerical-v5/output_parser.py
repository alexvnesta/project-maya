"""Independent strict parser for the frozen33ede finite numerical witness."""
import json

PAIRS = ((22, 22), (22, 17), (22, 16), (17, 22), (17, 17),
         (17, 16), (17, 18), (16, 22), (16, 17), (16, 16))
MAX_BYTES = 2 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def contract(job):
    require(type(job) is dict and set(job) == {'id', 'n', 'mode', 'pair'}, 'Exact job fields')
    n, mode, pair = job['n'], job['mode'], job['pair']
    require(type(n) is int and n in (256, 2304, 5120), 'Exact dimension')
    require(type(mode) is str and mode in ('optimized', 'fallback'), 'Exact dispatch mode')
    mixed = pair is not None
    if mixed:
        require(type(pair) is list and len(pair) == 2 and all(type(v) is int for v in pair)
                and tuple(pair) in PAIRS and n != 256, 'Actual mixed pair only')
    gu, down = pair if mixed else (17, 17)
    key = f'mixed-{gu}-{down}-{n}-{mode}' if mixed else f'pure-{n}-{mode}'
    require(job['id'] == key, 'Job identity differs')
    tested = down if n == 2304 else gu
    paths = {256: 2, 2304: 4, 5120: 6}[n] - (0 if tested in (17, 18) else 1)
    return gu, down, mixed, tested, paths


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def parse(stdout, stderr, job):
    gu, down, mixed, tested, paths = contract(job)
    require(type(stdout) is bytes and len(stdout) <= MAX_BYTES and type(stderr) is bytes
            and not stderr, 'Bounded stdout and empty stderr required')
    text = stdout.decode('utf-8')
    require(text.endswith('\n') and '\r' not in text, 'Complete LF output required')
    lines = text.splitlines(); mode = job['mode']; n = job['n']
    expected = [f'DISPATCH type=17 one={int(mode == "optimized")} multi={int(mode == "optimized")} expected={mode}']
    measured_own = None
    if mixed:
        require(len(lines) >= 2, 'Mixed dispatch missing')
        prefix = f'MIXED_DISPATCH gu={gu} down={down} tested={tested} selected_own='
        suffix = f' direct_rows1={int(tested in (17, 18))}'
        require(lines[1] in (prefix + '0' + suffix, prefix + '1' + suffix), 'Mixed dispatch differs')
        measured_own = int(lines[1][len(prefix)])
        # The fixture explicitly requires selected type17 to use the native path.
        require(tested != 17 or measured_own == 0, 'Type17 selected dispatch differs')
        expected.append(lines[1])
    for nt in ((1, 16) if mixed else range(1, 17)):
        for pad in (0, 32):
            for pattern in range(6):
                for lo, hi in ((0, 7), (1, 6), (3, 3)):
                    expected.append(f'PASS gu={gu} down={down} n={n} nt={nt} pad={pad} pattern={pattern} range={lo}:{hi} paths={paths}')
    require(len(lines) == len(expected) + 1 and lines[:-1] == expected, 'Exact ordered finite row inventory required')
    final = json.loads(lines[-1], object_pairs_hook=unique_object,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    wanted = {'status': 'PASS', 'gu_type': gu, 'down_type': down, 'n': n,
              'cases': 72 if mixed else 576, 'paths_per_case': paths, 'mixed': mixed, 'expect': mode}
    require(type(final) is dict and set(final) == set(wanted) and
            all(type(final[k]) is type(v) and final[k] == v for k, v in wanted.items()),
            'Exact typed final JSON required')
    return {'passed': True, 'job': job, 'cases': wanted['cases'], 'paths_per_case': paths,
            'selected_own': measured_own, 'type17_dispatch': mode, 'final': final,
            'scope': 'Finite synthetic exact-row witness only; no model quality or timing claim'}
