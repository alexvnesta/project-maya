// Correctness-only isolated target. No model, timing loop, benchmark or implicit other test.
#include "../src/ds4/ds4_iq.cuh"
#include "../src/ds4/ds4_iq2s_persist_policy.hpp"
#include "../src/ds4/ds4_gguf.cuh"
#include <cuda_runtime.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
namespace iq = strata::ds4::gguf::iq;
namespace gg = strata::ds4::gguf;
namespace x3 = strata::kernels::exl3;
#define CU(expr) do { const auto e = (expr); if (e != cudaSuccess) throw std::runtime_error(std::string(#expr) + ": " + cudaGetErrorString(e)); } while (0)
void require(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
template<class T> struct Buffer {
    T* p = nullptr; size_t n;
    explicit Buffer(const std::vector<T>& v): n(v.size()) {
        CU(cudaMalloc((void**)&p, n * sizeof(T)));
        CU(cudaMemcpy(p, v.data(), n * sizeof(T), cudaMemcpyHostToDevice));
    }
    ~Buffer() { if (p) cudaFree(p); }
    Buffer(const Buffer&) = delete;
    Buffer& operator=(const Buffer&) = delete;
    void put(const std::vector<T>& v) { require(v.size() == n, "buffer size"); CU(cudaMemcpy(p, v.data(), n*sizeof(T), cudaMemcpyHostToDevice)); }
    std::vector<T> get() const { std::vector<T> v(n); CU(cudaMemcpy(v.data(), p, n*sizeof(T), cudaMemcpyDeviceToHost)); return v; }
};
uint32_t next(uint32_t& s) { return s = s * 1664525u + 1013904223u; }
struct Experts {
    int D, F, type; size_t off[3], blob; std::vector<uint8_t> bytes; Buffer<uint8_t>* gpu;
    Experts(int d, int f, int t): D(d), F(f), type(t), blob(0), gpu(nullptr) {
        for (int r=0;r<3;++r) { off[r]=blob; blob += (((r<2?F:D)*iq::row_bytes(type,r<2?D:F)+255)/256)*256; }
        bytes.resize(4*blob); uint32_t seed=1849;
        for (auto& b:bytes) b=(uint8_t)(next(seed)>>24);
        const int bb=iq::block_bytes(type);
        for (int e=0;e<4;++e) for(int r=0;r<3;++r) {
            const size_t n=(r<2?F:D)*iq::row_bytes(type,r<2?D:F);
            for(size_t k=0;k<n;k+=bb) { // finite normal half scale, all quantized code/sign bits retained
                bytes[e*blob+off[r]+k]=0; bytes[e*blob+off[r]+k+1]=0x20;
            }
        }
        gpu=new Buffer<uint8_t>(bytes);
    }
    ~Experts() { delete gpu; }
    unsigned long long ptr(int e) const { return (unsigned long long)(gpu->p+e*blob); }
    x3::ExpertLayout layout() const {
        x3::ExpertLayout l{}; l.fmt=gg::kFmtMXFP4;
        for(int r=0;r<3;++r) { l.trellis[r]=off[r]; l.gg_type[r]=type; } return l;
    }
};
int cases=0;
void checked(const std::vector<float>& a,const std::vector<float>& b) {
    require(a.size()==b.size() && std::memcmp(a.data(),b.data(),a.size()*4)==0,"bit mismatch");
    for(float x:b) require(std::isfinite(x),"nonfinite output");
}
void direct(Experts& e,int ne,bool grouped,bool empty,unsigned cap,int pattern,cudaStream_t stream) {
    const int entries=128, guard=16, groups=6; const float sentinel=987.25f;
    std::vector<unsigned long long> plan(groups), gp(groups);
    for(int g=0;g<groups;++g) { plan[g]=g==1?0:e.ptr(g%4); gp[g]=e.ptr(g%4); }
    std::vector<int> starts{0}, ent, mask(entries,0);
    for(int g=0;g<groups;++g) {
        const int n=g==0?ne:g==2?std::max(1,ne-1):g==3?1:0;
        for(int t=0;t<n;++t) ent.push_back(t*8+g);
        starts.push_back((int)ent.size());
    }
    if(grouped && !empty) for(int x:ent) mask[x]=1;
    if(!grouped && !empty) for(int g=0;g<groups;++g) mask[g]=plan[g]!=0;
    if(empty && !grouped) std::fill(plan.begin(),plan.end(),0ull);
    Buffer<unsigned long long> pp(plan), pg(gp);
    Buffer<int> ps(starts), pe(ent), ng(std::vector<int>{empty?0:4});
    uint32_t seed=921;
    std::vector<int8_t> xq((size_t)16*e.D),hq((size_t)entries*e.F);
    for(auto* v:{&xq,&hq}) for(auto& x:*v) x=pattern==1?0:pattern==2?127:pattern==3?-127:(int8_t)((int)(next(seed)%255)-127);
    std::vector<float> xd((size_t)16*e.D/32,pattern==3?std::ldexp(1.0f,-140):0.0078125f);
    std::vector<float> hd((size_t)entries*e.F/32,pattern==3?std::ldexp(1.0f,-140):0.015625f);
    Buffer<int8_t> qx(xq),qh(hq); Buffer<float> sx(xd),sh(hd);
    std::vector<float> init_h(guard+(size_t)entries*e.F+guard,sentinel),init_y(guard+(size_t)entries*e.D+guard,sentinel);
    Buffer<float> h(init_h),y(init_y); iq::Args a{};
    a.plan_ptr=pp.p; if(grouped) { a.grp_ptr=pg.p; a.grp_start=ps.p; a.grp_ent=pe.p; a.n_groups=ng.p; }
    for(int r=0;r<3;++r) a.tr[r]=e.off[r];
    a.n_embd=e.D; a.n_ff=e.F; a.limit=10; a.tg=a.td=e.type;
    a.xq=qx.p; a.xd=sx.p; a.hq=qh.p; a.hd=sh.p; a.h=h.p+guard; a.part=y.p+guard;
    std::vector<float> ref_h,ref_y;
    for(int on=0;on<2;++on) {
        h.put(init_h); y.put(init_y); iq::set_iq2s_persist_for_test(on,cap);
        require(iq::gate_up(a,groups,grouped?ne:1,stream),"gate dispatch");
        require(iq::down(a,groups,grouped?ne:1,stream),"down dispatch");
        CU(cudaGetLastError()); CU(cudaStreamSynchronize(stream));
        const auto c=iq::iq2s_persist_test_counts();
        require(c.gate==(unsigned)(on && e.type==iq::kIQ2_S) && c.down==c.gate &&
                c.fallback==(unsigned)(!on && e.type==iq::kIQ2_S)*2,"actual dispatch counts");
        auto gh=h.get(),gy=y.get();
        for(int role=0;role<2;++role) {
            const auto& v=role?gy:gh; const int width=role?e.D:e.F;
            for(size_t i=0;i<v.size();++i) {
                const bool write=i>=guard && i<guard+(size_t)entries*width && mask[(i-guard)/width];
                require(std::isfinite(v[i]),"nonfinite direct");
                if(!write) require(v[i]==sentinel,"canary or inactive entry changed");
                else require(v[i]!=sentinel,"live output not written");
            }
        }
        if(!on) {ref_h=gh;ref_y=gy;} else {checked(ref_h,gh);checked(ref_y,gy);}
    }
    ++cases; std::printf("PASS direct D%d F%d type%d ne%d grouped%d empty%d cap%u pattern%d\n",e.D,e.F,e.type,ne,grouped,empty,cap,pattern);
}
void public_token(Experts& e,cudaStream_t stream) {
    std::vector<unsigned long long> ptr{e.ptr(0),0,e.ptr(2),e.ptr(3),e.ptr(0),e.ptr(1),0,0};
    Buffer<unsigned long long> pp(ptr);
    std::vector<float> x(e.D),shared(e.D,0.01f),cpu(e.D,0.02f),weights(8,0.25f);
    for(int i=0;i<e.D;++i) x[i]=(float)(i%31-15)/32;
    Buffer<float> dx(x),ds(shared),dc(cpu),dw(weights),h(std::vector<float>((size_t)8*e.F)),y(std::vector<float>(e.D));
    Buffer<int> cf(std::vector<int>{1}); x3::MoeArgs a{};
    a.plan_ptr=pp.p; a.plan_w=dw.p; a.cpu_part=dc.p; a.cpu_flag=cf.p; a.lay=e.layout();
    a.k=6; a.n_embd=e.D; a.n_ff=e.F; a.limit=10;
    std::vector<float> reference;
    for(int on=0;on<2;++on) {
        iq::set_iq2s_persist_for_test(on,1);
        gg::moe_gate_up(a,dx.p,h.p,stream); gg::moe_down(a,h.p,ds.p,y.p,stream);
        CU(cudaGetLastError()); CU(cudaStreamSynchronize(stream)); auto got=y.get();
        const auto c=iq::iq2s_persist_test_counts();
        require(on?(c.gate>0 && c.down>0 && c.fallback==0):(c.fallback>0 && c.gate==0 && c.down==0),"public token route did not exercise selection");
        if(!on) reference=got; else checked(reference,got);
    }
    ++cases; std::printf("PASS public_token D%d F%d\n",e.D,e.F);
}
void public_window(Experts& e,cudaStream_t stream) {
    constexpr int T=4, K=6;
    std::vector<unsigned long long> plan(T*8,0),gp;
    std::vector<float> x((size_t)T*e.D),shared(x.size(),0.01f),cpu(x.size(),0.02f),weights(T*8,0.25f);
    for(size_t i=0;i<x.size();++i) x[i]=(float)((int)(i%31)-15)/32;
    for(int t=0;t<T;++t) for(int k=0;k<K;++k) if(k!=1) plan[t*8+k]=e.ptr(k%4);
    std::vector<int> starts{0},ent;
    for(int g=0;g<4;++g) {
        gp.push_back(e.ptr(g));
        for(int t=0;t<T;++t) for(int k=0;k<K;++k) if(k!=1 && k%4==g) ent.push_back(t*8+k);
        starts.push_back((int)ent.size());
    }
    Buffer<unsigned long long> pp(plan),pg(gp); Buffer<int> gs(starts),ge(ent),ng(std::vector<int>{4}),cf(std::vector<int>(T,1));
    Buffer<float> dx(x),ds(shared),dc(cpu),dw(weights),h(std::vector<float>((size_t)T*8*e.F)),part(std::vector<float>((size_t)T*8*e.D)),y(std::vector<float>((size_t)T*e.D));
    x3::WinArgs a{}; a.grp_ptr=pg.p; a.grp_start=gs.p; a.grp_ent=ge.p; a.n_groups=ng.p;
    a.plan_ptr=pp.p; a.plan_w=dw.p; a.cpu_part=dc.p; a.cpu_stride=e.D; a.cpu_flag=cf.p;
    a.x=dx.p; a.x_stride=e.D; a.h=h.p; a.part=part.p; a.sh_out=ds.p; a.out=y.p; a.out_stride=e.D;
    a.lay=e.layout(); a.T=T; a.k=K; a.n_embd=e.D; a.n_ff=e.F; a.limit=10;
    std::vector<float> reference;
    for(int on=0;on<2;++on) {
        iq::set_iq2s_persist_for_test(on,1);
        require(gg::win_experts(a,stream),"public window dispatch");
        CU(cudaGetLastError()); CU(cudaStreamSynchronize(stream)); auto got=y.get();
        const auto c=iq::iq2s_persist_test_counts();
        require(on?(c.gate>0 && c.down>0 && c.fallback==0):(c.fallback>0 && c.gate==0 && c.down==0),"public window route did not exercise selection");
        if(!on) reference=got; else checked(reference,got);
    }
    ++cases; std::printf("PASS public_window D%d F%d\n",e.D,e.F);
}
int main(int argc,char** argv) {
    if(argc!=3 || std::strcmp(argv[1],"--iq2s-persist-check")) { std::fprintf(stderr,"expected --iq2s-persist-check 0|1\n"); return 2; }
    const int device=iq::iq2s_policy::check_device(argv[2]);
    if(device<0 || iq::iq2s_policy::literal_mode(std::getenv("STRATA_DS4_Q8_BATCH"))!=1 ||
       iq::iq2s_policy::literal_mode(std::getenv("DS4_Q8_CHECK"))!=1) {
        std::fprintf(stderr,"exact device0|1 and Q8 batch/check1 required\n"); return 2;
    }
    try {
        CU(cudaSetDevice(device)); int major=0; CU(cudaDeviceGetAttribute(&major,cudaDevAttrComputeCapabilityMajor,device));
        require(major>=8,"SM80+ required"); std::string error;
        require(gg::q8_batch() && gg::q8_batch_check(device,error),"selected Q8 check");
        cudaStream_t stream; CU(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
        for(const auto shape:{std::pair<int,int>{512,256},{5120,2304}}) {
            Experts e(shape.first,shape.second,iq::kIQ2_S);
            for(unsigned cap:{0u,1u}) {
                direct(e,1,false,false,cap,0,stream);
                for(int ne:{1,2,4,5,8,9,16}) direct(e,ne,true,false,cap,0,stream);
                direct(e,1,true,true,cap,0,stream);
                direct(e,1,false,true,cap,0,stream);
            }
            for(int pattern:{1,2,3}) direct(e,2,true,false,1,pattern,stream);
            public_token(e,stream);
            public_window(e,stream);
        }
        { Experts other(512,256,iq::kIQ2_XS); direct(other,1,false,false,1,0,stream); direct(other,5,true,false,1,0,stream); }
        iq::set_iq2s_persist_for_test(-1); CU(cudaStreamDestroy(stream));
        require(cases==52,"case inventory"); std::printf("ALL %d IQ2_S checks passed device%d\n",cases,device); return 0;
    } catch(const std::exception& e) { std::fprintf(stderr,"FAIL %s\n",e.what()); return 1; }
}
