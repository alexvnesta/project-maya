// CPU policy and integer-sum/rounding controls.
// Does not compile or execute CUDA kernels and is not GPU numerical qualification.
#include "../src/ds4/ds4_cache_admission.hpp"
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <vector>
#include <cmath>

static uint32_t bits(float x) { uint32_t y; std::memcpy(&y, &x, sizeof y); return y; }
static int count = 0;
static void pass(const char* id) { ++count; std::printf("PASS %s\n", id); }

int main() {
    using strata::ds4::cache_migration_worthwhile;
    constexpr size_t MB = 1024 * 1024;
    assert(!cache_migration_worthwhile(6.0f,4.0f,1.25f,1.0f,10*MB,0));
    assert(cache_migration_worthwhile(6.001f,4.0f,1.25f,1.0f,10*MB,0));pass("P01_legacy_strict_boundary");
    for (int cold=0;cold<100;++cold) for(int hot=0;hot<250;++hot)
        assert(cache_migration_worthwhile((float)hot,(float)cold,1.25f,1.0f,0,0)==(hot>cold*1.25f+1.0f));
    pass("P02_disabled_policy_exact_legacy_grid");
    assert(!cache_migration_worthwhile(13.99f,4,1.25f,1,10*MB,2));
    assert(cache_migration_worthwhile(14,4,1.25f,1,10*MB,2));pass("P03_two_transfer_price_boundary");
    assert(cache_migration_worthwhile(14,4,1.25f,1,10*MB,2));
    assert(!cache_migration_worthwhile(14,4,1.25f,1,11*MB,2));pass("P04_larger_expert_costs_more");
    assert(!cache_migration_worthwhile(100,90,1.25f,1,MB,100));pass("P05_price_does_not_bypass_hysteresis");
    for (double price : {-1.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()})
        assert(!cache_migration_worthwhile(30,4,1.25f,1,MB,price));
    pass("P06_invalid_prices_refuse");
    assert(!cache_migration_worthwhile(std::numeric_limits<float>::infinity(),4,1.25f,1,MB,2));
    assert(!cache_migration_worthwhile(30,std::numeric_limits<float>::quiet_NaN(),1.25f,1,MB,2));pass("P07_nonfinite_heat_refuses");
    assert(!cache_migration_worthwhile(30,4,1.25f,1,0,2));
    assert(!cache_migration_worthwhile(30,4,1.25f,1,std::numeric_limits<size_t>::max(),2));pass("P08_zero_and_huge_size_refuse");
    uint32_t rng=0x79a81u;auto random=[&](){rng=rng*1664525u+1013904223u;return rng;};
    for (int trial=0;trial<10000;++trial) {
        std::array<int8_t,32> x;std::array<uint8_t,32> w;
        for(int i=0;i<32;++i){x[i]=(int8_t)((int)(random()%256)-128);w[i]=(uint8_t)(random()%32);}
        int sl=0,sh=0,lo=0,hi=0;
        for(int i=0;i<16;++i){sl+=x[i];sh+=x[i+16];lo+=(int)w[i]*x[i];hi+=(int)w[i+16]*x[i+16];}
        int sl4=0,sh4=0,lo4=0,hi4=0;
        for(int g=0;g<4;++g)for(int j=0;j<4;++j){int i=4*g+j;sl4+=x[i];sh4+=x[i+16];lo4+=(int)w[i]*x[i];hi4+=(int)w[i+16]*x[i+16];}
        assert(sl==sl4&&sh==sh4&&lo==lo4&&hi==hi4);
        float d=(float)(1+random()%8192)/1024.0f,m=(float)(random()%8192)/4096.0f;
        int scale=(int)(random()%64);
        float a=d*(float)(scale*lo+scale*hi)-(m*(float)sl+m*(float)sh);
        float b=d*(float)(scale*lo4+scale*hi4)-(m*(float)sl4+m*(float)sh4);
        assert(bits(a)==bits(b));
    }
    pass("P09_shared_half_sums_and_float_order_10000_rows");
    bool differs=false;
    for(int i=1;i<10000&&!differs;++i){float m=(float)i/100003.0f;volatile float a=m*2032.0f,b=m*-2016.0f;differs=bits(a+b)!=bits(m*16.0f);}
    assert(differs);pass("P10_negative_control_combined_minimum_changes_rounding");
    for(int k : {256,5120,7168,8192,32768})for(int nc=1;nc<=16;++nc){
        size_t n=(size_t)k/32*nc,bytes=n*2*sizeof(int);std::vector<int> seen(2*n,0);
        for(size_t tid=0;tid<256;++tid)for(size_t i=tid;i<n;i+=256){++seen[i];++seen[n+i];}
        for(int value:seen)assert(value==1);
        assert(bytes==seen.size()*sizeof(int));
    }
    pass("P11_shared_index_coverage_all_columns_and_shapes");
    assert((size_t)8192/32*16*2*sizeof(int)==32768);
    assert((size_t)32768/32*16*2*sizeof(int)>32768);pass("P12_shared_memory_bound_and_fallback");
    std::printf("SUMMARY %d controls PASS; CUDA/native/runtime UNRUN\n",count);
}
