"""Lossless byte/layout controls against an independent adjacent-nibble oracle."""
import hashlib
import math
import os
from pathlib import Path
import subprocess
import unittest

def reference(weights,scales):
    result=bytearray()
    for block,scale in enumerate(scales):
        codes=[]
        for packed in weights[block*16:(block+1)*16]:codes.extend([packed&15,packed>>4])
        result.append(scale)
        result.extend(codes[j] | (codes[j+16]<<4) for j in range(16))
    return bytes(result)

class Codec(unittest.TestCase):
    def run_codec(self,rows,k,body,*,args=None):
        exe=Path(os.environ['MXPACK_CPU_BINARY'])
        return subprocess.run([str(exe),*(args if args is not None else ['--rows',str(rows),'--k',str(k)])],input=body,capture_output=True,timeout=20,check=False)
    def test_all_nibble_values_and_scale_bytes(self):
        weights=bytes(range(256))*16;scales=bytes(range(255))+b'\x00'
        r=self.run_codec(256,32,weights+scales);self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,reference(weights,scales));self.assertEqual(r.stderr,b'')
    def test_rows_and_block_order_with_independent_oracle(self):
        for rows,k in [(1,32),(2,64),(7,128),(13,256)]:
            blocks=rows*k//32;weights=bytes((i*37+11)%256 for i in range(blocks*16));scales=bytes((i*17)%255 for i in range(blocks))
            r=self.run_codec(rows,k,weights+scales);self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,reference(weights,scales))
    def test_every_logical_value_matches_original_fp4_e8m0(self):
        source=[0,.5,1,1.5,2,3,4,6,0,-.5,-1,-1.5,-2,-3,-4,-6]
        doubled=[0,1,2,3,4,6,8,12,0,-1,-2,-3,-4,-6,-8,-12]
        weights=bytes(range(16))*6;scales=bytes([0,1,126,127,128,254]);r=self.run_codec(6,32,weights+scales);self.assertEqual(r.returncode,0)
        for b,e in enumerate(scales):
            for j in range(32):
                src=(weights[b*16+j//2]>>(4*(j%2)))&15
                dst=(r.stdout[b*17+1+j%16]>>(4*(j//16)))&15
                self.assertEqual(src,dst);self.assertEqual(math.ldexp(source[src],e-127),math.ldexp(doubled[dst],e-128))
    def test_full_original_gate_up_geometry_and_bytes(self):
        rows,k=2304,5120;blocks=rows*k//32;weights=(bytes(range(256))*((blocks*16+255)//256))[:blocks*16];scales=(bytes(range(255))*((blocks+254)//255))[:blocks]
        r=self.run_codec(rows,k,weights+scales);self.assertEqual(r.returncode,0);self.assertEqual(len(r.stdout),6266880)
        expected=reference(weights,scales);self.assertEqual(hashlib.sha256(r.stdout).digest(),hashlib.sha256(expected).digest())
    def test_truncation_and_extra_input_never_emit(self):
        for body in [b'',b'\x00'*15,b'\x00'*16,b'\x00'*18]:
            r=self.run_codec(1,32,body);self.assertEqual(r.returncode,3);self.assertEqual(r.stdout,b'')
    def test_nan_scale_refused_before_any_output(self):
        r=self.run_codec(2,32,b'\x00'*32+b'\x7f\xff');self.assertEqual(r.returncode,4);self.assertEqual(r.stdout,b'')
    def test_invalid_or_oversized_geometry_before_allocation(self):
        for rows,k in [(0,32),(2305,32),(1,0),(1,31),(1,5121),(-1,32),(1,-32),('999999999999999999999',32)]:
            r=self.run_codec(rows,k,b'');self.assertEqual(r.returncode,2);self.assertEqual(r.stdout,b'')
        r=self.run_codec(1,32,b'',args=['--other','1','--k','32']);self.assertEqual(r.returncode,2)

if __name__=='__main__':unittest.main()
