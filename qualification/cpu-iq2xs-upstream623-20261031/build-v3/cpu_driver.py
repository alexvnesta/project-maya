"""Portable build-v3 custody/CPU lease controls. Temporary lock contenders only; no compiler/native/GPU execution."""
import argparse
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
R = HERE.parents[3]
REMOTE = Path('/home/alex/strata-deepseek-test-20261024')
CPU_SECONDS = 30
AS_BYTES = 512 * 1024 * 1024
WALL_SECONDS = 90
RUN_SECONDS = 85  # leaves five seconds of the parent wall allowance for owned cleanup
ENV = {'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
       'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1', 'MALLOC_ARENA_MAX': '1',
       'PYTHONDONTWRITEBYTECODE': '1'}
SOURCES = ('build.py', 'test_build.py', 'cpu_driver.py', 'test_cpu_driver.py')
TEST_MODULES = ('test_build', 'test_cpu_driver')
INPUTS = {'/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/adaptive-expert-cache-v1/SELECTED_CPU_LINK_OBSERVATION.json': '0a4d3f3fa2141afdab5f43f47eff11c014aa74558cb6d5a3c5d3765899164f0b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/adaptive-expert-cache-v1/SELECTED_CPU_SOURCE_BUILD_OBSERVATION.json': '7025fb879bc350998dc6de3aa3d58c5a490c1248046bf8c6eba580514d28e1ee',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/adaptive-expert-cache-v1/upstream-PR623-files-20261031T0438.json': 'c215f2fa974c7295635d99d7a3d893135263964740d1f56ff24d723e28aae62b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-darwin/attempt.json': '218898456b90ae4d618d99a31f598929a64f8a58a6f98a5ec2857c0e4cf9df74',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-darwin/child.json': '003e7e69dabc74fb351ad7fbaa9ffc84154a9a2f98d322ddd36099ccd0cfeb6b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-darwin/child.log': 'a1c758d76f1315cb11d73034ba0d6be52ffc3a1a72e084dd39882f1dac645d40',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-darwin/observed.json': '694a3568bf8ba57bed52ca42f14855f90e665d67ea172c62803d16740da52328',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-darwin/parent.json': '7effdfce92b2876405eee4bcc44e78eddf34eca018e131e6a79eff33a0e71ae9',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-darwin/receipt.json': '2c6c8dd4f837c0fadd10c63cff0ad7bc05270cb231bb7f686d64f7d224ed3f39',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-linux/attempt.json': '90862c61a587cc8239eaabb325f482d0917e6e386d0cf5143244e56441746fa8',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-linux/child.json': '4ab4fcceb99c99a9d5b9459213cf4f0716c2f1d935e7da97753c50daabc98e27',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-linux/child.log': '279ae9fa62cacc02cb451e8c2c18300eb78017cf746b17a560d96d71d583cea4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-linux/observed.json': 'd41267fc9600eed4ddde4c4a0d0ad4c7f7f80ca5ce26803dd4a410e3eb03811a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-linux/parent.json': '030fbddf53d0c02643d64ad0facb314ad4cb3474169cf05b08abbc7fe86c9f1c',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU-FIRST-linux/receipt.json': '98e3f6d7018095c32471673fcf52878f8e6fb2011d56cc3b73ec50d9f0a33dcb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/CPU_RESULT_ASTRA_REVIEW.json': 'e36b462e9fcc300513645cf57730b5a96a99a0cc21c169840a37129a56bd4aff',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/SELECTED_MAIN_EXPERT_FORMATS_ROOT.json': '6f88898634629b9a7ec5fd5e7f54346e72f9bb8af1c11a76253463084c8113e6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/SOURCE_ROOT_REVIEW.json': 'ed420b79292d99e9eb8e087647bd068dd906bb0c466800ea007574f49aa132cd',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/include/strata/kernels/cpu/iq_avx2.hpp': '878cafbeef8144fd4e0b48f492f4812985ab4544dfb06c14523903a46821cd74',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/include/strata/kernels/cpu/native_expert.hpp': 'c22c92c0d18a6c045f9534d52b8cad51a8c8f25c58b2e138991d1708a9cdd050',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/src/ds4/ds4_iq_cpu.cpp': '7894f430fdfb48ba030ee9aff21414833e7f498052d322aeb33b53655da6118a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/src/kernels/cpu/iq_avx2.cpp': 'e4dddd81e6c657d677fff4f92c8a1167f0634ed323301ec2396bf30f231b81d4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/base/src/kernels/cpu/native_expert.cpp': '29c706324adaf639e553f266bda6ca1c0c6d755746622e1e80f0af0dbafa3de4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-darwin/attempt.json': '32c3a1396ae6e9f6cdaffae3f1fb8a8b4021a1b84ec6eae4b290eb27e457b315',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-darwin/child.json': '109e22d192c9256d14503a076ca2bb86a721e96b249692742c624065f7980112',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-darwin/child.log': '34c71f167fed88d8419db6451908f3071e3cf1fa8c1f7eac036223d262d9e0e8',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-darwin/observed.json': '393da11cca3c545222bfada52d8bccf516c42026b12235b2da3794d79caf978d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-darwin/parent.json': 'c6ee2c71c479014d1f9f60ff402c7ebd2d497abd0ab4e4efa0b99a2bae13d94a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-darwin/receipt.json': '9581aa0107a9ed501480b1a4c47582761286b26a483f46e7aac4a31d833d4049',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-linux/attempt.json': '60d62922ee78018391de82a933aa7a1b0841ee81080991ef98c57504b72a555c',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-linux/child.json': '3fb5dcb9b018aea463b446976bfec921670c54dc3dd44561449a8275b00c3be6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-linux/child.log': 'b9e90b263d93b8b477d43f21f097eddf3f46624ba2f58437af6d58861290d7d7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-linux/observed.json': '028bf14ab972e36527b61b52c42e5f2f4700f9495897d77952610b4a85aae489',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-linux/parent.json': '0398fddbd5793879aed5c5ecb373cce0748a8eb3d11279cfcaf4927be4d76c8f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU-FIRST-linux/receipt.json': '9f58778e1cbae158cce3fe797a833063b4df1d6fa2154edd2201c653fee2829f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU_RESULT_ASTRA_REVIEW.json': '07d7e8188e23b3c03397a59a7b1bae9316d31547e22e569677302cd1ef846ce2',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/CPU_ROOT_RESULT_REVIEW.json': '2edd3f38c26b20c5f8d1da8e2de3a7ae30eb6bfe18cb5f28f018ce3e2c6185d0',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/DEPENDENCY_OBSERVATION.json': '484eef58045e75b899a22bc5db5854a85c972ce21f039b570431852b22a500f3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/LINK_TOOL_CLOSURE_OBSERVATION.json': 'ab969d6c4eac98ceccec860719ade4304c010c0e031ccea85d2ccde59929d129',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/PREPARE_PREFLIGHT_LOCK_DEFERRAL.json': 'fbf2077836c3e95f47acc6a5a79cc91f95c47c6944bdf8978a276cb5e1468b68',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/SELECTED_HOST_GPU_LEASE_UNIT_OBSERVATION.json': 'dca285e51698c828ad7c85bda698c37c079dddb4484162fade78547ced9751fc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/SOURCE_ROOT_REVIEW.json': '9e675dd36a295c2b20b9c8c0b1f67c84f6b2f833b2c1091a3fd551ecb74fdca5',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/build.py': 'e78c258135fe48455627d2bca53310324d35427841ed8b9a35c4f64d3fc99358',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/cpu_driver.py': 'c82f6669438e00d20e04c47ed5b183373d7ebb48dbc2bcfafe215a1eb96bba6d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/prepare-qualification.json': 'd3f71e656e153aac2d56fdce0b03c2c324dae50c89e3a305e0d6035d2a92ee63',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/test_build.py': '5c39bf49476fdf69bbbf5bdb88b73bfc016c9085a046466ef4c91beff6a9e7d1',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v1/test_cpu_driver.py': 'b33e52afb6735cec6f0842b2121682b781cbb304ca2ccec800a0997b4ec4dd47',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/ARCHITECTURE_ASTRA.json': '6eb9dbf704a14cfb09d9c1537e2a1ffe0f16c131aceeaa9d33e491e0903dbb5a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-darwin/attempt.json': '11f0d20181f42605f5ba3c4c68a6908f467342bf0ea758d86132e62099c30651',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-darwin/child.json': '81f6afd2f8c0b99a11cd9e9b3531fbf8959b08209636fc35b1a9f431c5fb7a26',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-darwin/child.log': '50464022f60c1e6ea15100545d410e389daf5e9225ab1f5c3bbf5b7ef41a1622',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-darwin/observed.json': '58924996e2d2f14376cc1eee1ce5bf602db785124e9a28187da432510778822d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-darwin/parent.json': '9e7f28472cdb575b6d1ee109a79dff2b28362993fa142237a929e8abc60d99c8',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-darwin/receipt.json': '2eac8de2e438da51f773131bb5bef8dff2a6ee1b2d87aa4736d3ad234e715632',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-linux/attempt.json': 'adc7350c6f0924a50b3b4b39315f9de56370383253dc217f9b40021eb5eff2da',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-linux/child.json': '488b501227b3d0e172d7b23d79a5484a861e9372ab699c857be557b690d2e5e5',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-linux/child.log': '796065c2eb63d3e0ae424127ecd6ebd78525c88ce26d69b72cded0d67f6a135a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-linux/observed.json': '31bd8e979eea4f060e1c8e4a7393a20697bbe4e9a7d018bfbf68422300262182',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-linux/parent.json': '6776df64fb5cfc8ffeafb5ef882744d11433b0a0d212c9779f11480a0bb3256e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU-FIRST-linux/receipt.json': '4feb40b559be76bab8204a48ff769b0e920455014696892ffa1ab6c2506f2edb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU_RESULT_ASTRA_REVIEW.json': '8256986a5530d35f2d1d25e7de142a94124f5586de584a150d2980e69becc9f5',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/CPU_ROOT_RESULT_REVIEW.json': '51518fc1f52d841689cf4e9aa126538b0505f1b06a6facb344004b43d0e7def9',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/PREPARE_ADMISSION_ASTRA.json': 'c83296a7a7d2ed67efb1f3cec9f054c363ee855e542652e8d5c3bc62acac350d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/PREPARE_STARTUP_FAULT_HOLD.json': 'a17af202135ebb447b913bbe1a04c99c88593474d21cfe3c18cce2b3b3fecd7d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/SOURCE_ROOT_REVIEW.json': 'ddf72767adba7f4172517ab9f870666ecff07c2c07ba8c177828bb7c34ba7a96',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/build.py': 'c8fe2d0b4d14de534b3b52c2e06327fe6e3b642f5aad366f2bd68458a70e4c3b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/cpu_driver.py': '151773c37dd3475273b4ae680334badfb1b957d2b650f23a44996f00ca049f58',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/prepare-controller.stderr': 'dce24db64e3975ea18911bd93cb8df52f4474092c79135ceb3a936c57760be9b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/prepare-controller.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/prepare-qualification.json': 'b22c1468268c55bb9559aac1b38f343339dcb9d0c5e523d148876c421c7ede2a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/test_build.py': '93ab3bf34d820b36782ddb5451efd02ef7b58ac84ba70a7c063bd9ab4fbef9b7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v2/test_cpu_driver.py': 'b33e52afb6735cec6f0842b2121682b781cbb304ca2ccec800a0997b4ec4dd47',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate.patch': '639cb7c533827cee486c7bfdffafe5ae6d102fbdc20c3efb67778c9980b4bf43',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/include/strata/kernels/cpu/iq_avx2.hpp': '669943775b48a05f87ff5984dd1c05df94185d7a7f73e693c830df67b9bc71c7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/include/strata/kernels/cpu/native_expert.hpp': 'af881c474d3896b996de8068f7aaed6918ac2f303172c55d59d663a40cb2ac0e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/src/kernels/cpu/iq_avx2.cpp': '0f2151cd0b1e4a77467e132ba92d2cea626f92fd079508ef393c5622b2d71edb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/src/kernels/cpu/native_expert.cpp': '614191b7aef3bf15dacb3b04c8ef5a1b390b8a28ffbb13e2195430c5f0be3120',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/cpu_driver.py': '3fed5bef32fa584b08f2dfb684ddf944d39ce02d5daa48e0bd07eb94f8b02707',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/inputs/selected-tensors.txt': 'bc5229fa509356053d07bbcc97e1245f05ac29934c9f92605b21659b4675c966',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v2/iq2xs_exact.cpp': '33ede583a7c299a9bac83520050a6ea48233ae596fe6bb0a0f8195dbb7dfd6e7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/source_contract.py': '6d116441cb559a5e136eaae4f5bfc148cb2e02b8b85808a270ed83e182b51e68',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/test_cpu_driver.py': 'b33e52afb6735cec6f0842b2121682b781cbb304ca2ccec800a0997b4ec4dd47',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/test_source_contract.py': '8f979db35e72b52e9524065322feea2addab759301941770a0b91f0ca3e4b595',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/tests/iq2xs_exact.cpp': '46054c27abe0538fea5d3c58c0c7585a40ba89c2002a3ca4e7abd98491dc8b6b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/iq2s-persistent-v1/iq2s_build.py': 'e8dcd79bd3a80cba931885149438f107d6d840693e508f738fd616fd6885f9ff',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/maya-s-comparison-v1/model-v1/selected-ds4_model.cu': 'dfe326d6a60d77354c8c92fb14ec423a92afff76b91f0810104f0a54a51a6350',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/model-v1/numerical-qualification.json': '6eb179b8b7edb7a87133c4e24bd99dc2f35863cfe6ef56f8385590bf50c6315b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/prose-speed-v1/prose_measure.py': '8d10d003bbbd7ffbb87251bacdf53d91af9f074151d34f06c957fa179f3108cf',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/prose-speed-v1/transport.py': 'cd026ab8cc86228500f606efb0913e55a63ba89b4e55fbfc33707b18c595bf37',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/selected-pack-quant-inventory-FIRST.json': '55a170d4e8c2dc758f19fb21f4b36836b91b43036ddc213599954b5378011f07'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
            not path.is_symlink() and path.stat().st_nlink == 1,
            'One regular pinned file required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(REMOTE),
            'Canonical input path required')
    return R / path.relative_to(REMOTE)


def test_ids():
    ids = []
    for module in TEST_MODULES:
        tree = ast.parse((HERE / (module + '.py')).read_text())
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                ids.extend(module + '.' + cls.name + '.' + f.name for f in cls.body
                           if isinstance(f, ast.FunctionDef) and f.name.startswith('test_'))
    require(ids and len(ids) == len(set(ids)), 'Literal nonempty unique controls required')
    return sorted(ids)


def checked(review_pin):
    require(isinstance(review_pin, str) and len(review_pin) == 64 and
            all(c in '0123456789abcdef' for c in review_pin), 'Exact review pin required')
    review_path = HERE / 'SOURCE_ROOT_REVIEW.json'
    require(digest(review_path) == review_pin, 'Manual review bytes changed')
    review = json.loads(review_path.read_text())
    require(review.get('root_entire_new_source_tests_and_candidate_delta_read') is True and
            review.get('astra_entire_new_source_tests_and_candidate_delta_read') is True, 'Both manual reads required')
    actual = {name: digest(HERE / name) for name in SOURCES}
    require(review.get('source_sha256') == actual, 'Exact source map required')
    require(INPUTS and review.get('input_sha256') == INPUTS, 'Exact literal input map required')
    require({key: digest(local(key)) for key in INPUTS} == INPUTS, 'Input bytes changed')
    ids = test_ids()
    require(review.get('test_ids') == ids, 'Exact current ordered controls required')
    return actual, dict(INPUTS), ids


def environment():
    env = dict(os.environ)
    for name in ('PYTHONPATH', 'PYTHONHOME'):
        env.pop(name, None)
    env.update(ENV)
    return env


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (AS_BYTES, AS_BYTES))
    nice = os.getpriority(os.PRIO_PROCESS, 0)
    require(nice <= 15, 'Unexpected inherited nice')
    os.nice(15 - nice)


def observed():
    return {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgid(0),
            'cpu': list(resource.getrlimit(resource.RLIMIT_CPU)),
            'as': list(resource.getrlimit(resource.RLIMIT_AS)) if sys.platform == 'linux' else None,
            'nice': os.getpriority(os.PRIO_PROCESS, 0),
            'environment': {k: os.environ.get(k) for k in ENV}, 'platform': sys.platform,
            'dont_write_bytecode': sys.dont_write_bytecode}


def bounds(actual, pid, parent):
    require(type(pid) is int and pid > 1 and actual.get('pid') == pid and
            actual.get('ppid') == parent and actual.get('pgid') == pid, 'Actual child identity/group required')
    require(actual.get('cpu') == [30, 30] and actual.get('nice') == 15 and
            actual.get('environment') == ENV and actual.get('dont_write_bytecode') is True,
            'Actual child bounds/environment required')
    require(actual.get('platform') in ('linux', 'darwin'), 'Physical supported host required')
    require(actual.get('as') == ([AS_BYTES, AS_BYTES] if actual['platform'] == 'linux' else None),
            'Actual address-space bound required')


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def cleanup(process, owned_pgid, deadline):
    """Only the new-session group created for this exact Popen handle is eligible."""
    require(type(owned_pgid) is int and owned_pgid > 1 and owned_pgid == process.pid and
            owned_pgid != os.getpgrp(), 'Owned group identity refused')
    if process.poll() is None:
        require(os.getpgid(process.pid) == owned_pgid, 'Live child changed group')
    if group_alive(owned_pgid):
        try:
            os.killpg(owned_pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=min(0.2, max(0.001, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            pass
    if group_alive(owned_pgid):
        try:
            os.killpg(owned_pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
    while group_alive(owned_pgid) and time.monotonic() < deadline:
        time.sleep(0.01)
    require(not group_alive(owned_pgid), 'Owned descendants survive cleanup')


def supervise(argv, folder, *, run_seconds=RUN_SECONDS, wall_seconds=WALL_SECONDS):
    require(0 < run_seconds < wall_seconds <= 90, 'Bounded run and cleanup budget required')
    folder = Path(folder)
    require(folder.is_dir() and not folder.is_symlink(), 'Owned attempt directory required')
    started = time.monotonic(); process = None
    result = {'argv': list(argv), 'pid': None, 'returncode': None, 'error': None, 'cleanup': []}
    try:
        with (folder / 'child.log').open('xb') as stream:
            process = subprocess.Popen(argv, cwd=HERE, env=environment(), stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, start_new_session=True,
                                       preexec_fn=limits)
            result['pid'] = process.pid
            result['returncode'] = process.wait(timeout=run_seconds)
            require(result['returncode'] == 0, 'Child nonzero')
    except BaseException as exc:
        result['error'] = repr(exc)
    finally:
        if process is not None:
            try:
                cleanup(process, process.pid, started + wall_seconds)
            except BaseException as exc:
                result['cleanup'].append(repr(exc))
            result['returncode'] = process.poll()
        result['elapsed_seconds'] = time.monotonic() - started
        with (folder / 'child.json').open('x') as f:
            json.dump(result, f, indent=2); f.write('\n')
    return result


def flatten(suite):
    return [case.id() for item in suite for case in
            (flatten_cases(item) if isinstance(item, unittest.TestSuite) else [item])]


def flatten_cases(suite):
    out = []
    for item in suite:
        out.extend(flatten_cases(item) if isinstance(item, unittest.TestSuite) else [item])
    return out


def attempt_contract(value, review_pin, parent_pid, before):
    require(value == {'review_sha256': review_pin, 'parent_pid': parent_pid,
                      'source_sha256': before[0], 'input_sha256': before[1], 'test_ids': before[2]},
            'Exact parent attempt custody required')


def child(review_pin, folder, parent_pid):
    actual = observed()
    bounds(actual, os.getpid(), parent_pid)
    before = checked(review_pin)  # before any project/test import
    require(folder.parent == HERE and folder.name == 'CPU-FIRST-' + sys.platform and
            folder.is_dir() and not folder.is_symlink(), 'Exact first attempt required')
    digest(folder / 'attempt.json')
    attempt_contract(json.loads((folder / 'attempt.json').read_text()), review_pin, parent_pid, before)
    with (folder / 'observed.json').open('x') as f:
        json.dump(actual, f, indent=2); f.write('\n')
    sys.path.insert(0, str(HERE))
    suite = unittest.TestSuite()
    for name in TEST_MODULES:
        module = importlib.import_module(name)
        require(Path(module.__file__).resolve() == HERE / (name + '.py'), 'Test module origin changed')
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    require(flatten(suite) == before[2], 'Actual loader order differs from frozen IDs')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = checked(review_pin)
    require(after == before, 'Inputs changed during controls')
    post = observed(); bounds(post, actual['pid'], parent_pid)
    require(post == actual, 'Child bounds changed')
    receipt = {'status': 'PASS' if result.wasSuccessful() else 'FAIL', 'pid': actual['pid'],
               'review_sha256': review_pin, 'source_sha256': before[0], 'input_sha256': before[1],
               'source_after_sha256': after[0], 'input_after_sha256': after[1],
               'test_ids': before[2], 'tests_run': result.testsRun, 'observed': actual,
               'post_observed': post, 'failures': len(result.failures), 'errors': len(result.errors)}
    with (folder / 'receipt.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    return 0 if result.wasSuccessful() else 1


def parent(review_pin):
    before = checked(review_pin)
    require(sys.platform in ('linux', 'darwin'), 'Physical supported host required')
    folder = HERE / ('CPU-FIRST-' + sys.platform)
    folder.mkdir()  # exclusive; failure/partial proof is never overwritten
    with (folder / 'attempt.json').open('x') as f:
        json.dump({'review_sha256': review_pin, 'parent_pid': os.getpid(),
                   'source_sha256': before[0], 'input_sha256': before[1], 'test_ids': before[2]}, f, indent=2)
    argv = [sys.executable, '-I', '-B', str(HERE / 'cpu_driver.py'), '--child',
            '--review-pin', review_pin, '--parent-pid', str(os.getpid())]
    result = supervise(argv, folder)
    require(result['returncode'] == 0 and result['error'] is None and not result['cleanup'] and
            result['elapsed_seconds'] <= 90, 'Actual child/cleanup failed; preserve first attempt')
    require(checked(review_pin) == before, 'Post-child input change')
    receipt = json.loads((folder / 'receipt.json').read_text())
    actual = json.loads((folder / 'observed.json').read_text())
    bounds(actual, result['pid'], os.getpid())
    require(receipt.get('status') == 'PASS' and receipt.get('pid') == result['pid'] and
            receipt.get('review_sha256') == review_pin and receipt.get('observed') == actual and
            receipt.get('post_observed') == actual and receipt.get('failures') == 0 and
            receipt.get('errors') == 0 and receipt.get('tests_run') == len(before[2]) and
            receipt.get('test_ids') == before[2] and receipt.get('source_sha256') == before[0] and
            receipt.get('source_after_sha256') == before[0] and receipt.get('input_sha256') == before[1] and
            receipt.get('input_after_sha256') == before[1], 'Exact successful child receipt required')
    with (folder / 'parent.json').open('x') as f:
        json.dump({'status': 'PASS', 'pid': result['pid'], 'review_sha256': review_pin,
                   'receipt_sha256': digest(folder / 'receipt.json'),
                   'child_sha256': digest(folder / 'child.json'),
                   'log_sha256': digest(folder / 'child.log')}, f, indent=2)
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--review-pin', required=True)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    if args.child:
        require(args.parent_pid is not None, 'Parent identity required')
        sys.exit(child(args.review_pin, HERE / ('CPU-FIRST-' + sys.platform), args.parent_pid))
    require(args.parent_pid is None, 'Parent-only arguments refused')
    sys.exit(parent(args.review_pin))
