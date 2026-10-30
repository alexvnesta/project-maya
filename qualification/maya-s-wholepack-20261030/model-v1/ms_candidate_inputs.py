"""One new explicit CPU encoding operation for constructed published Maya-S.

Requires full source/CPU admission before invoking; no model or weight reading.
No baseline re-encoding, fallback tokenizer or request resizing is permitted.
"""
from pathlib import Path
import ms_fixtures as fixtures


def validate(manifests):
    fixtures.require(type(manifests) is dict and set(manifests)=={'quality','prose','coding'},'Exact three candidate families required')
    pins=None;template=None
    for mode,m in manifests.items():
        fixtures.require(m['mode']==mode and m['context']==1048576 and m['default_output']==262144
                         and m['pack_relative_to_E']==str(fixtures.CANDIDATE_PACK.relative_to(fixtures.E))
                         and fixtures.packed(m['policy'])==fixtures.packed(fixtures.POLICY),'Exact published pack/request capacity required')
        fixtures.require(m['request_source_sha256']==fixtures.SOURCE_PINS and m['API_sha256']==fixtures.SUPPORT_PINS['native-vision-v2/runtime/serve/server.py'],
                         'Changed request/API source identity')
        fixtures.validate_encoded(m['cases'],mode)
        if mode=='prose':fixtures.validate_encoded(m['lifecycle_cases'],'lifecycle')
        else:fixtures.require(m['lifecycle_cases']==[],'Unexpected unmeasured lifecycle family')
        if pins is None:pins=m['tokenizer_source_sha256'];template=m['effective_template']
        fixtures.require(m['tokenizer_source_sha256']==pins and m['effective_template']==template,
                         'Candidate tokenizer/template changed between families')
    return manifests


def produce():
    # tokenizer_bytes validates exact approved candidate directory and its five
    # real nonaliased metadata files. No expert payload or pack build occurs.
    fixtures.tokenizer_bytes(fixtures.CANDIDATE_PACK)
    value={mode:fixtures.build_manifest(fixtures.CANDIDATE_PACK,mode) for mode in ('quality','prose','coding')}
    return validate(value)
