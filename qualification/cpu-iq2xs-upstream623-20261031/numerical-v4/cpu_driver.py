"""Portable numerical-v4 parser/supervisor controls; no numerical ELF or model execution."""
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
SOURCES = ('runner.py', 'output_parser.py', 'test_runner.py', 'test_output_parser.py', 'cpu_driver.py', 'test_cpu_driver.py')
TEST_MODULES = ('test_cpu_driver', 'test_output_parser', 'test_runner')
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
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/COMPILE_ACTUAL_PREFLIGHT.json': 'ba67b25ca642331a6548fcc9ff42534c1ee48c73010dd5238d458b6ede6552df',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/COMPILE_ADMISSION_ASTRA.json': '1c399ea9ff89653759469fd1385833b1bb0f445013219c96345b6dde0cbd95b0',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/COMPILE_PRODUCTION_CLOSURE.json': '69697830bbc88d7727470f08d3af0a9beb140e604a53f38e4b63d1f3577af855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/COMPILE_RESULT_ASTRA_REVIEW.json': '35a968a7482c06062a56f15901cddab25c6db2109a700f1c1c099e9e7dde960a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/COMPILE_ROOT_RESULT_REVIEW.json': 'cf1bfc5fef8f9fa387754005285dd34ea6c53c05a58a95821be0e63d2e96ccd2',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-darwin/attempt.json': 'dad6abbae8622abd546728e291a93edd7734e5ff0918047f8fea193b09bb8487',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-darwin/child.json': 'dbb50717292c00e084c6f6380fe7f1c8ad5b11c515be5178c655872ca9a6ea68',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-darwin/child.log': 'ab954981ad0a9cd21b58f70862eb11386f6ad26c7ebee8046c15296f634a4e8d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-darwin/observed.json': 'a676da726c998431f59dff4c7d2d52c646462916dfccf08e985e5dfd5ce6e72b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-darwin/parent.json': '6c4b24a2e689d86fe9063d4e900086c1b8a2deaddb310e1cc57ec40a0c6f1bc9',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-darwin/receipt.json': 'ee26a1a311ba9615c5731a67b7f2881e63a87dba27f92b101b73b6f02a2172c3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-linux/attempt.json': '82c11cfffde680dd41aa86de367720149412f4bf87bacbdff1f8760a90f7f6ea',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-linux/child.json': '6dd8c4bd3a67333473a6aab6a9ebc60495415f1493e70cb92b7b3e4230dfd321',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-linux/child.log': '0e932162330df34d3fe394641996364b72b53e6ee30eb3130ae8a5854ead8fd4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-linux/observed.json': '2ac84215ebed0366135fac6711ca014cacda199b33673e3feaf99841d83b18ff',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-linux/parent.json': '39124b67a8c9da0e0b0a844cb8beaaf78320823b65ebebb32b530f46f2ffd3ab',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU-FIRST-linux/receipt.json': 'f9bb674e9c2832047c0927d9d9eda0cf4a5d4cbb5450e3be351a8d37170ac28f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU_RESULT_ASTRA_REVIEW.json': '4b8923643e7729f0f0720ff028503d8721fe0b3c957d1061366405b6694f72cb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/CPU_ROOT_RESULT_REVIEW.json': '2f43d9559fd7d785670e51bfcf4a74edd0f271075c3ec7cdd5924e860651e1b3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/SOURCE_ASTRA_REVIEW.json': '6af3248fffc9bf6731c34083af0efaf756b5c42c8deb900a6a701aba995b3509',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/SOURCE_ROOT_REVIEW.json': '72afc1f0f4b2b65ff0272ac46176bf9fc85f7267e40e1f66d8f39d3f8901bf56',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-index.json': 'b1b6b5e9e195215872fa7c53b4cbea588549e208df0953d1b1742657abb9ddfa',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-index.observed.json': '9c9e2bb03be44e0d44820672aa626fa416faca8c02b54d290dfaad3b12c11e61',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-index.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-index.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-replace.json': '778387fdb312415364113ec7f74d14cede3962728694bddad6640ef0d6c5dd69',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-replace.observed.json': 'f5a9fa039f98f8116daed6ff30dfa5e31cc1eb5815273dc48de14d0c47b4d76d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-replace.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/archive-replace.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/candidate-link-inputs.json': 'd1d1169d52f208330c1f07341c2c6dd07beae05900d8b3e1867803b57ca5877e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/candidate-link.json': '5e25d718bbfd6a3881451704fb00457fb003754e8b4349c8ae6eee606cbe71dc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/candidate-link.observed.json': 'ba75163d8c4faf037a8100e70ff4db275140375e84f4cb09f69a366be0dcaeb3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/candidate-link.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/candidate-link.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq2xs_exact.cpp-inputs.json': 'b29470c461a69ba7f162a211f0b2da7ca5693b829c272c1a8758ee8b0e15f841',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq2xs_exact.cpp.json': '8eeed7fc31ef20692d3149056590a21497383be9bdcf57eb4fbecaa7a17975de',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq2xs_exact.cpp.observed.json': '54e7155fde5fda77a9a8550a947bafa64215b13de01dcf5d240ab424e0359281',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq2xs_exact.cpp.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq2xs_exact.cpp.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq_avx2.cpp-inputs.json': 'd68f06d0d6ba528841f8fa63538199597575bb967c67c1aa217fdfcf9a2485ff',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq_avx2.cpp.json': 'e0eff4ec9fbc6e549a1f39d9fd212b23a286b041c0e6cee992a5f303c2b28ff4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq_avx2.cpp.observed.json': 'b8971fa43052a7e5a0bf63d82001899076325e25906186a83e2f9cf81e471db0',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq_avx2.cpp.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-iq_avx2.cpp.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-native_expert.cpp-inputs.json': 'c9b131ed19452b233510977c699b39dc629d11f539e2540276dbe66fd83332c9',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-native_expert.cpp.json': '255ae5866913645c7e4847b95542836019bdd7fb91af20460f8dda317130c673',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-native_expert.cpp.observed.json': 'fd8ca9d1ebf42a657cfab03e1f01d6993f8756b6c7ee3bd53ca8570cd585d9d5',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-native_expert.cpp.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/compile-native_expert.cpp.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/fixture-link-inputs.json': 'bb5547c654eb5c3d10c95190d8f011ff5ec2ba013cf4b487fad4b75f7be117c7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/fixture-link.json': '545271f3faad95967bb2c07036a82536d4f1f5464e9ffde70a76d933ab6ccebc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/fixture-link.observed.json': '32f20270c4bdc3d3cbba8a399631a6f2f56d659c0a9ad9518e52afae2d643279',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/fixture-link.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/fixture-link.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/iq2xs_exact.cpp.o.d': '2359fe978b99e08e9bb52dcd63477d8dba01ba2f45ea2def9c009842d25942c7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/iq2xs_exact.link.d': '8d16ea5037734d78ecb7b3f13e61740d2ec83f52d9d6b529431bc060e9a2a612',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/iq_avx2.cpp.o.d': '63e76532aec085da12eed53f77197ebad31c208e075fe6c9f61c93df519249bb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/maya-ds4-candidate.link.d': 'aecf4d9774c36b6cab758542cb3d4aabec8d0e7993068963287bca1d8830c9bb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/native_expert.cpp.o.d': '41aec876a7b6382bc295b36dfe650a01caa498d2880aaa09ccd8f0a4f50a6d5a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build-FIRST/receipt.json': '85c91ec88a9ab5c985570f0646ce4577439188b98d32055e6e3c791183b9587f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/build.py': 'a765195c6fc6fe65e2d780bce3d166d28f181de722d68d725f7bceb568dd7380',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/compile-controller.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/compile-controller.stdout': '040a77c8b7f0163c866c0589a522ed3f57e8f893405a62a19ac14d3caa693cb2',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/compile-qualification.json': '64acb1becb8ea7b61fa5867578bc46347f667a78ae864071ed6791decf0d9e08',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/compile-supervision-FIRST/attempt.json': '2c8f6baea7675aee98967b19c7eef20597434f2461aaa37527f147e8e7d40369',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/compile-supervision-FIRST/owned-children.jsonl': 'bc9f246737342ab3f3c01482e65e7e1a0673138edc1fbecae7e48e3a8228c5e5',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/compile-supervision-FIRST/result.json': 'ae27471dd43ffcf73c87c18cb5c35797b5723a1bc69ee4c21a58b357766ba9b3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/cpu_driver.py': '879533ad6a29f28082299984b42341b619fb228c17f5676d9e090b9409206d39',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/prepare-FIRST/receipt.json': 'a238a3360d49a2ca60570b2f85eef616b71c9f65b7a2f02dcf992285ecc60b6f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/test_build.py': '151557f6042d2cf1aed270480650564d54aede16ad74ab0b43ea3186299063cf',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/build-v3/test_cpu_driver.py': 'b33e52afb6735cec6f0842b2121682b781cbb304ca2ccec800a0997b4ec4dd47',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate.patch': '639cb7c533827cee486c7bfdffafe5ae6d102fbdc20c3efb67778c9980b4bf43',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/include/strata/kernels/cpu/iq_avx2.hpp': '669943775b48a05f87ff5984dd1c05df94185d7a7f73e693c830df67b9bc71c7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/include/strata/kernels/cpu/native_expert.hpp': 'af881c474d3896b996de8068f7aaed6918ac2f303172c55d59d663a40cb2ac0e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/src/kernels/cpu/iq_avx2.cpp': '0f2151cd0b1e4a77467e132ba92d2cea626f92fd079508ef393c5622b2d71edb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/candidate/src/kernels/cpu/native_expert.cpp': '614191b7aef3bf15dacb3b04c8ef5a1b390b8a28ffbb13e2195430c5f0be3120',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/cpu_driver.py': '3fed5bef32fa584b08f2dfb684ddf944d39ce02d5daa48e0bd07eb94f8b02707',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/ACTUAL_PREFLIGHT.json': 'e2cd1e3df1e326508a92f202a58c22f79e461f7a2a2ee33099a7c895ba484446',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/ARCHITECTURE_ROOT_AGREEMENT.json': 'c9d9a2d7d82707ec8f6aff0eb1aa7eb28706e666cfc3206d33bc51438f043738',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/BUILD_ADMISSION_ASTRA.json': 'be91466cd7c7c99939aeaa555adb96ab4aed8f2f5263dad22548b2edc5b710df',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/BUILD_PRODUCTION_CLOSURE.json': '4fae0dd887fd564b9ab18fc4cf4e99f75da3a3b790a4bc783b6b09410ced6604',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/BUILD_RESULT_ASTRA_REVIEW.json': '1777c14c9744b4b09ff9480b93386757f62f6a98234b4116d55745feb46e2cc5',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/BUILD_ROOT_RESULT_REVIEW.json': 'c39b6f2c106e18149b741b67f0b5c691396f8866b9387aec8a054da40519aaf4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-darwin/attempt.json': 'c86dace4ce075243ade84afdd69d0addd23434ccc9a7ad8e8a055debd0f5e1da',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-darwin/child.json': '885f4b4b63fa5e1198062cdf8ed8ce6c81172850c7e84227b762c26cbe532d21',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-darwin/child.log': '9aab1d58d1260042aa271bfe565933cc189af82127bb14b1803af0283502d9a6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-darwin/observed.json': '234151523cfe4c8209aadbe7be0ee1c80021eacdd1322bc6a29c6468f4f2367b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-darwin/parent.json': 'e647ed1aa91cacacaba90a627804d9855cea3d33c57b5fa0d504ad57a1d95636',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-darwin/receipt.json': '9e0fb92095e6684b07d575ad0dca88f6bd346dbfce54e9d6e811f6cc764de243',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-linux/attempt.json': 'b652d73689bbc7a2c73addcaf5b35b8c5413eaa3c49630b5a8566cb135462de6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-linux/child.json': '0c72fc470ea165853e8e115972c2c5fa75bd525816eec445bf24aaadd48723bf',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-linux/child.log': 'ad894f0f6bd2fb43446891804a490f479bda9bd8ca7ae958e0b4f89658ee120b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-linux/observed.json': 'ad3beba71857bcdfed42340f349bdd7330130d8d67ff9f315289925d574d6489',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-linux/parent.json': '3b07eb04a9e266071dae6d626c2c63394fd0d7f6b28fe2b6782a63dda9c0b96f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU-FIRST-linux/receipt.json': '394a1630d46823e5dc1cb94be0b436ffa6dfd02b8b5b1e9fce94851e53de7639',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU_RESULT_ASTRA_REVIEW.json': 'e02765dd98f910e7c8bfb2c4afaf800ce1682fde4bd3c6d5fe9bb22c0ad94bb1',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU_ROOT_RESULT_REVIEW.json': 'bed2052d0f4a0bd98788aa63bff39eb05eecf2d5dab279897c8bb5ef196e7c19',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/CPU_STAGE_IDLE_PREFLIGHT.json': '17e58cc45c633e1f5db02821a77c2002cfdf2a0a3fbc0a8e2e299243c17cbe89',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/MAP_ASTRA_REVIEW.json': 'fe94593dd8dbe8f98db0e57a1d43914834bd501630525ccd971d34386544f0a9',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/MAP_ROOT_REVIEW.json': '8b3262d0a59fb4025946fb0ccf53dc36be4b5a021deeec8b8269fa53af33af24',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/METADATA_STAGE_RECEIPT.json': 'eb7c2a19657ec2eb84425bb0436e35ba2b7b21c02106fa27b563f774fa63d825',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/SOURCE_ASTRA_REVIEW.json': '123ab0ab1372d76a289701a47cfb437d1bf2160df4f9f2c0468ba53e02c85763',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/SOURCE_ROOT_REVIEW.json': '31bc5323cfc18160a9192e500d1b2530d3454d45c07a2c9899fad4ec8039374c',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-compile-inputs.json': '7e2f844d8d993f4e0fb6c3dcc8559f612f204572028d371c9a2d82b12bf0bf61',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-compile.json': 'a13c5914e24f972e09d8178d832940ebc4e78201abae3889cdce21ce1b2710cb',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-compile.observed.json': 'c468d7b68aa20ffd79ffca756098df6c83c1b8dcc53feb4a1a0a975128c9e2cd',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-compile.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-compile.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-link-inputs.json': '829d8e279648190589aa2f32c314fe831cd7450a3fffeae4143a7ed1474ae10d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-link.json': '3371eb366970607dbff02b0cf5ea981d4d67bd66383234ab81a56c5bc83c4998',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-link.observed.json': 'eaf9aeda67ef5a2298190bb2d621d14ad6a28097c517087ba0460acb3adea8c6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-link.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/fixture-link.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/iq2xs_exact.cpp.o.d': 'b84014936255a7d53296f7ab24c91d97bbee26f73a6ff538f61a7639bc08d48e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/iq2xs_exact.link.d': 'f2d6656684c37bf0ff29c6bef643e82c24fd6607f6cb20613c063ed077d52bd8',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-FIRST/receipt.json': '035e4a12735f1936ada3cf4543fda457c2fb7a61ce6bba63ff712a8d5f76481a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-supervision-FIRST/attempt.json': '6691413388f080f9effa95c52b5b1e1a09df3be8ffcf4ce15157927ce5e882a4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-supervision-FIRST/owned-children.jsonl': 'b8d9019d2ceed630a6d592c1ddd7d8ba738344ed93fbccc4e7b9aecbc7ecd40f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build-supervision-FIRST/result.json': 'f7318c01e3f104a8082e1b3ea978bcf42e2204ac0bc3a8289e475659348aeaf1',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/build.py': 'd2af840efc5989dcc5de6174f4b11a3ebd7c9da2ecc8c14e630ec41e4982bea7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/controller.stderr': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/controller.stdout': 'ae2d8f7376b5eba975f932e6275524cf6f36e8c5224526ee14b1b6e3b0292ba1',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/cpu_driver.py': '730fb023fed65e17894d2a9b2d019131458a53ff13b070fc9ea61c0f27a38e33',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/iq2xs_exact.cpp': '559daba1f5e18a7cc7d2ddc91f0850e215997ab39d955e9b7e8fd751d05e4b25',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/qualification-DRAFT.json': '135fa085babf934ac75c8db30d0034c21f20c96e1e2e7c2ba9b4abf86bb58da6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/qualification.json': '01acb187f2c74475783666ecc04e5013b0fa06c11b8a72ef34b7a6bdcc921658',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/test_build.py': '205e0af60639f7d271268e3250d1c4595005a3653119e55ac59104c7eaddedda',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/fixture-repair-v4/test_cpu_driver.py': 'b33e52afb6735cec6f0842b2121682b781cbb304ca2ccec800a0997b4ec4dd47',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/inputs/selected-tensors.txt': 'bc5229fa509356053d07bbcc97e1245f05ac29934c9f92605b21659b4675c966',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v2/iq2xs_exact.cpp': '33ede583a7c299a9bac83520050a6ea48233ae596fe6bb0a0f8195dbb7dfd6e7',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/ACTUAL_PREFLIGHT.json': '2fc85c73f9e4a94ded2a207989dcdf13d730a2236a25e966dd16a7a2f21a032d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/ARCHITECTURE_ASTRA.json': '085941f0095762e5f7ef73fd22cdc1c201acd26204227e7cadf21504bbb2f62f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/ARCHITECTURE_ROOT_AGREEMENT.json': '91dbb7c148ea7c8233c9c10dc4e8afb7f26c255e59f738c3b10f6c856f62b7e0',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-darwin/attempt.json': '385e6ea1db03d57126107ea730ba8f1374d458b6fa46c71199188ab440c94732',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-darwin/child.json': 'dc96f34ecf91e0d2d3def656f83da0c3f5b59bb307f93507f8036f1476588cbf',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-darwin/child.log': '5dcb8ebe59f9170ff3b4e0db1d1886bb943e63f41f9fda92a3111164f4bac0a8',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-darwin/observed.json': '0514cf0895a4c71b3217451d92274247da9d47b440bc6a8cd4edfa72f72f6f32',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-darwin/parent.json': 'e5c923100b25d01096f65fca1f75219673d3a131baaaf480eed7cf311f070026',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-darwin/receipt.json': 'a250a1e77fc13291a85d39419f15ac01fa91d6cbc50bcef6ede62a5fca317e87',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-linux/attempt.json': 'ed53147f3853f112031997f6005d488134526babc10ed14e88f4dff6c074631a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-linux/child.json': '98829f4f1813835b2a0d59bb8b6a44e8bc69f6c6ee34899a17167b3964a56dc6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-linux/child.log': '2e2c8356a468132cbf47fccba6bf2727b906507fa8668036493972afccc3a636',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-linux/observed.json': 'd9f9cad2090f4f0589f198ba317e1fbe74300954755deace8437b5e7449d3f34',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-linux/parent.json': '87d593ce78670a6795e1f695952f986a86b94804900eaf9ff61babfc23521adc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU-FIRST-linux/receipt.json': '41edef51a24e10ddb5f9e652aff4a956519dcc81a99e51e4be672d0bf3165ea2',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU_RESULT_ASTRA_REVIEW.json': '20d2144a30146b4ad56a2e7493b9e790ee6bb0fba0b6bde0eec19cbffb7e075b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU_ROOT_RESULT_REVIEW.json': '8dd913c049a4aa348905c19d2baeb7433c408f5338da18554cf3fe90f67ca78e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/CPU_STAGE_IDLE_PREFLIGHT.json': '9127774a1c5db273239a3c8cf9d393a1fd217a5c61ed6deaa739714ea4e52c94',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/FIRST_FAULT_ASTRA_REVIEW.json': '9b680d35d25ab8459d23918cc74bc2fe57dedbf8ae51b0ee5566983bc35258ba',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/FIRST_FAULT_ROOT_REVIEW.json': '1fe3b4858745259cf45819ca37bc692089f517416c841a9b1d6633a44ddce2ff',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/GGML_QUANTIZER_SOURCE_OBSERVATION.json': 'c35c80858b1e6e98b2bef9086ac4fef2f4de616818a492cad621944dae0252b4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/HOLD_PRODUCTION_CLOSURE.json': '59bed4035a85f5a721db34cbfe4a52f6acf5ca7e6610e02871f0810ef1f345bc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/MAP_ASTRA_REVIEW.json': '908324ccfbaf76baaf6632b7c5770b69e68443d4ad015443533ba56c455d33e8',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/MAP_ROOT_REVIEW.json': '99b1620867f9354be55af0ea50a3558f2c01c144404b21ca7372a5793dd2da0d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/METADATA_STAGE_RECEIPT.json': 'd5277de5edec2758e04e64238ed5da4347e9a2a7b70015f30788848c80565fb3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/NUMERICAL_ADMISSION_ASTRA.json': 'e1fc46c8442a93f16d89c3a4aeab6c2b40b62b448ebc66079da9c145a94bee91',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/PHYSICAL_CPU_CAPABILITY.json': 'f24529205339ff74715ccdda452a65e799d2a750024289c9b786d2cdc2f1b52e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/PROSPECTIVE_FIXTURE_REPAIR_ARCHITECTURE_ASTRA.json': '7914ac948088fcf6667db97c9782e9427d288a94b28186e0d8ebd03eb3d14a81',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/QUANTIZER_LINKED_MEMBER_OBSERVATION.json': 'dfcf33ed14816adf15c90831f8b04ceccf5c3516fb9abb6f8233d0920feea78c',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/SOURCE_ASTRA_REVIEW.json': 'cec91a112d6c47c8da5ad9b433c8631f30c5a406dc07fba5ec3d1ee9e7208c89',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/SOURCE_ROOT_REVIEW.json': '7986a3bb319c3637ad6a517f696467643d399a70db805207667cc3247a0aacbc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/controller.stderr': '34a9921e785793d99053f87060f3d6126c4ab65c0b430b61d9676e7b43fe5747',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/controller.stdout': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/cpu_driver.py': '8cc32d6321db15ad9ac4ad0fea22dfea639432d2c94506a02b377f3f0d3168d4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-FIRST/partial.json': 'ea48c23ac0e4de6df3219a134b567f30c502e7c38f56482c49674d48990ce8f3',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-FIRST/pure-256-optimized/child.json': '14758fbc52575011495f7ec7a94763e1998a39b83a46728cdf31d134b46f2bc2',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-FIRST/pure-256-optimized/dispatch-environment.json': 'b39da09e1567e278beeaf86c8ce584088275fe4c860ea3b6e5c27019e1d61f63',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-FIRST/pure-256-optimized/observed.json': '4a3152a1a4b81145d774690a87e59a62159d6404d9fa18119d62760ed101f81a',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-FIRST/pure-256-optimized/stderr': '537670122ee3703664cf1ff66ac95e9e896e4c53b4480841767030180b7a913f',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-FIRST/pure-256-optimized/stdout': 'ee058be323ed043834d8837eac75f2ef9b7730e4544be1185df6dd226f5614a0',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-supervision-FIRST/attempt.json': '3a27290479f2607e1b23aed151e28bd36222ff20c64e65cc03676f762416b5ee',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-supervision-FIRST/owned-children.jsonl': '1d318bb018eeb3960f68e57f7f473974e3f170b2fd5e3d8b64afc508d8e014dc',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/numerical-supervision-FIRST/result.json': 'd08d4b4830786819f750379982a29f4c950d8bce6888a7ea586787e571378a00',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/output_parser.py': 'bf4d9a463bd816eab4c8161100d230e417fe65c652a5fcccd1574564e4822bdd',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/qualification-DRAFT.json': '1c4b3a25fd190835f97a95cdb4b9b57f54d0d3b7da60450236dde304c7ff8ba4',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/qualification.json': '067bdfbd0caad55ac0715215e110734cb4659f7b4f448e61e791e5ae7e35bf8d',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/read-only-quantizer-disassembly/child.json': '2ffcbd3647c4a3969423b099a95dde98104bbd177b236a14687c169dde4ba8ad',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/read-only-quantizer-disassembly/child.log': 'c9c8fadecab815d536e9d76cc51a254d7e15ae1f08739c297c85bc843a3092e6',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/read-only-quantizer-disassembly/observation.json': '10ca322a47b89f76b58dcf2828fda50d7dc8734a7579430b1ec5496902871189',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/runner.py': '474098a4ebdf96d7b8e35b74c93b35ec363f3e0240c8003df09347cc29fcdd7e',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/test_cpu_driver.py': 'b33e52afb6735cec6f0842b2121682b781cbb304ca2ccec800a0997b4ec4dd47',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/test_output_parser.py': 'edd065bc56c998a3d6521967d43c004ea80c639b2fc572815795e5e6c22fa36b',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v3/test_runner.py': '9093f94bc0e738d2e063fee34fc78fff3055058469c602887acd7fad5bddb7a9',
 '/home/alex/strata-deepseek-test-20261024/reliability-optimization-20261025/decode-optimization-20261028/cpu-iq2xs-upstream623-v1/numerical-v4/PHYSICAL_CPU_CAPABILITY.json': 'f24529205339ff74715ccdda452a65e799d2a750024289c9b786d2cdc2f1b52e',
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
