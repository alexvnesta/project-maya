"""One new explicit CPU encoding operation for constructed published Maya-S.

Requires full source/CPU admission before invoking; no model or weight reading.
No baseline re-encoding, fallback tokenizer or request resizing is permitted.
"""
from pathlib import Path
import ms_fixtures as fixtures

CANDIDATE_TOKENIZER_PINS={
    'vocab.json':'2f0bf5b31f4aa191d5d0d78291927a4f28c9ceb498a5e345b97e926c4cb99c1a',
    'merges.txt':'547bace837acea98652eef5669c9b01cee1c73ad1d2a44d6fdce9e6a81c22147',
    'token_type.json':'0a61021438e5ce6041133495f18fc360a6587aea748b17d953f552d2119ba51e',
    'tokenizer.json':'5a47981b685b75154e29bfb0299584c9b3a4a28679585e86d524c34c065d037f',
    'chat_template.jinja':'753420ada6b529bbdeefe3c24932f948696a71dd36f54491ec951cbc44f40c16'}


def candidate_template():
    path=str((fixtures.CANDIDATE_PACK/'tokenizer/chat_template.jinja').relative_to(fixtures.E))
    return {'pack_template_relative_to_E':path,
            'pack_template_sha256':CANDIDATE_TOKENIZER_PINS['chat_template.jinja'],
            'effective_template_relative_to_E':path,
            'effective_template_sha256':CANDIDATE_TOKENIZER_PINS['chat_template.jinja'],
            'pack_template_replaced':False,
            'api_picker_sha256':fixtures.SUPPORT_PINS['native-vision-v2/runtime/serve/dsml.py'],
            'selection_policy':'EXACT_UNCHANGED_B1_DSML_PICKER_WITH_PINNED_V41_FALLBACK'}


def validate(manifests):
    fixtures.require(type(manifests) is dict and set(manifests)=={'quality','prose','coding'},'Exact three candidate families required')
    for mode,m in manifests.items():
        fixtures.require(m['mode']==mode and m['context']==1048576 and m['default_output']==262144
                         and m['pack_relative_to_E']==str(fixtures.CANDIDATE_PACK.relative_to(fixtures.E))
                         and fixtures.packed(m['policy'])==fixtures.packed(fixtures.POLICY),'Exact published pack/request capacity required')
        fixtures.require(m['request_source_sha256']==fixtures.SOURCE_PINS and m['API_sha256']==fixtures.SUPPORT_PINS['native-vision-v2/runtime/serve/server.py'],
                         'Changed request/API source identity')
        fixtures.validate_encoded(m['cases'],mode)
        if mode=='prose':fixtures.validate_encoded(m['lifecycle_cases'],'lifecycle')
        else:fixtures.require(m['lifecycle_cases']==[],'Unexpected unmeasured lifecycle family')
        fixtures.require(m['tokenizer_source_sha256']==CANDIDATE_TOKENIZER_PINS
                         and fixtures.packed(m['effective_template'])==fixtures.packed(candidate_template()),
                         'Exact actual candidate tokenizer/template required; no fallback')
    return manifests


def produce():
    # tokenizer_bytes validates exact approved candidate directory and its five
    # real nonaliased metadata files. No expert payload or pack build occurs.
    fixtures.tokenizer_bytes(fixtures.CANDIDATE_PACK)
    value={mode:fixtures.build_manifest(fixtures.CANDIDATE_PACK,mode) for mode in ('quality','prose','coding')}
    return validate(value)
