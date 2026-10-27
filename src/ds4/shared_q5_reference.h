// CPU-only proposed startup reference extension; NOT integrated into a native engine.
// Q5 decode copied from project-maya6afa src/ds4/ds4_q6k.cuh (MIT, vendor/MAYA-LICENSE).
// Per32 activation reference follows the same revision tests/ds4_gguf_test.cu102-114.
#pragma once
#include <algorithm>
#include <cmath>
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <limits>
#include <vector>
namespace q5_shared_cpu {
inline float q5k_f16_host(uint16_t h) {
    const uint32_t sign = (uint32_t) (h & 0x8000u) << 16, e = (h >> 10) & 0x1f, m = h & 0x3ff;
    uint32_t bits;
    if (e == 0) {
        if (m == 0) bits = sign;
        else {   // (subnormal: normalized)
            int sh = 0;
            uint32_t mm = m;
            while (!(mm & 0x400)) mm <<= 1, ++sh;
            bits = sign | ((uint32_t) (113 - sh) << 23) | ((mm & 0x3ff) << 13);
        }
    } else if (e == 31) bits = sign | 0x7f800000u | (m << 13);
    else bits = sign | ((e + 112) << 23) | (m << 13);
    float f;
    std::memcpy(&f, &bits, 4);
    return f;
}
inline void q5k_values(const uint8_t* b, float* y) {
    const float d = q5k_f16_host((uint16_t) (b[0] | b[1] << 8)), dmin = q5k_f16_host((uint16_t) (b[2] | b[3] << 8));
    const uint8_t *sc = b + 4, *qh = b + 16, *ql = b + 48;
    auto scale_min = [&](int j, int& s, int& m) {
        if (j < 4) {
            s = sc[j] & 63;
            m = sc[j + 4] & 63;
        } else {
            s = (sc[j + 4] & 0xF) | ((sc[j - 4] >> 6) << 4);
            m = (sc[j + 4] >> 4) | ((sc[j] >> 6) << 4);
        }
    };
    unsigned u1 = 1, u2 = 2;
    for (int j = 0, is = 0; j < 256; j += 64, is += 2, ql += 32, u1 <<= 2, u2 <<= 2) {
        int s, m;
        scale_min(is, s, m);
        const float d1 = d * (float) s, m1 = dmin * (float) m;
        scale_min(is + 1, s, m);
        const float d2 = d * (float) s, m2 = dmin * (float) m;
        for (int l = 0; l < 32; ++l) *y++ = d1 * (float) ((ql[l] & 0xF) + (qh[l] & u1 ? 16 : 0)) - m1;
        for (int l = 0; l < 32; ++l) *y++ = d2 * (float) ((ql[l] >> 4) + (qh[l] & u2 ? 16 : 0)) - m2;
    }
}
inline bool rounded_dense_input(const std::vector<float>& x,std::vector<float>& rounded) {
 if(x.empty() || x.size()%32 || std::fegetround()!=FE_TONEAREST)return false;
 for(float a:x)if(!std::isfinite(a))return false;
 rounded.assign(x.size(),0.0f);
 for(size_t b=0;b<x.size();b+=32){
  float am=0.0f;for(int j=0;j<32;++j)am=std::max(am,std::fabs(x[b+j]));
  const float sc=am/127.0f;
  if(am>0.0f && (sc==0.0f || !std::isfinite(sc)))return false;
  for(int j=0;j<32;++j){
   float q=am>0.0f ? std::nearbyint(x[b+j]/sc):0.0f;
   if(!std::isfinite(q) || q < -127 || q > 127)return false;
   rounded[b+j]=(float)((double)q*sc);
  }
 }
 return true;
}
inline bool gemv(const std::vector<uint8_t>& bytes,int rows,int k,const std::vector<float>& x,std::vector<float>& out){
 if(rows<=0 || k<=0 || k%256 || x.size()!=(size_t)k)return false;
 size_t stride=(size_t)(k/256)*176;
 if((size_t)rows>std::numeric_limits<size_t>::max()/stride || bytes.size()!=(size_t)rows*stride)return false;
 std::vector<float> xr;
 if(!rounded_dense_input(x,xr))return false;
 out.assign(rows,0.0f);float w[256];
 for(int row=0;row<rows;++row){
  double sum=0;
  for(int b=0;b<k/256;++b){
   q5k_values(bytes.data()+(size_t)row*stride+(size_t)b*176,w);
   for(int j=0;j<256;++j){if(!std::isfinite(w[j]))return false;sum+=(double)w[j]*xr[(size_t)b*256+j];}
  }
  out[row]=(float)sum;if(!std::isfinite(out[row]))return false;
 }
 return true;
}
} // namespace q5_shared_cpu
