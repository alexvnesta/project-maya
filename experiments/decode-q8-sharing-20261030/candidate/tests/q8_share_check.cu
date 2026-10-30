// Finite, correctness-only sharing check. No model, benchmark, or long-running loop.
#include "../src/ds4/ds4_gguf.cuh"
#include "../src/ds4/ds4_q8_share_policy.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <vector>
namespace gg = strata::ds4::gguf;
namespace p = strata::ds4::q8share;
namespace x3 = strata::kernels::exl3;
static void ck(cudaError_t e) {
    if (e != cudaSuccess) throw std::runtime_error(cudaGetErrorString(e));
}
static void need(bool yes, const char* why) { if (!yes) throw std::runtime_error(why); }
struct Buffer {
    void* p = nullptr;
    explicit Buffer(size_t bytes) { ck(cudaMalloc(&p, bytes)); }
    Buffer(const Buffer&) = delete;
    Buffer& operator=(const Buffer&) = delete;
    ~Buffer() { if (p) cudaFree(p); }
};
static void half_one(uint8_t* dst) { dst[0]=0; dst[1]=0x3c; }

static void one_case(int k, int nc, int n, int pattern, cudaStream_t stream) {
    constexpr int nj = 8, guard = 16;
    constexpr float sentinel = -987654.0f;
    const size_t ldx = static_cast<size_t>(k)+32, ys = static_cast<size_t>(n)+3;
    std::vector<float> x(static_cast<size_t>(nc)*ldx);
    for (size_t i=0; i<x.size(); ++i) {
        const int z=static_cast<int>((i*37+17)%253)-126;
        x[i] = pattern==0 ? static_cast<float>(z)/127.0f :
               pattern==1 ? (i%2 ? -0.0f : 0.0f) :
               i%4==0 ? 1e-25f : i%4==1 ? -1e-25f : static_cast<float>(z)*1e8f;
    }
    // B has identical bytes at a distinct address. A is also read with changed stride/row count.
    Buffer inputs(x.size()*sizeof(float)*2);
    float* dx=static_cast<float*>(inputs.p);
    for (int i=0;i<2;++i) ck(cudaMemcpy(dx+i*x.size(),x.data(),x.size()*sizeof(float),cudaMemcpyHostToDevice));
    std::vector<float> bias(n,0.125f);
    Buffer dbias(bias.size()*sizeof(float));
    ck(cudaMemcpy(dbias.p,bias.data(),bias.size()*sizeof(float),cudaMemcpyHostToDevice));
    x3::Mat mats[nj]{};
    x3::MvJob jobs[nj]{};
    const size_t each=2*guard+static_cast<size_t>(nc)*ys;
    Buffer output(nj*each*sizeof(float));
    std::vector<float> init(nj*each,sentinel), off(init.size()), on(init.size());
    // Separate allocations keep real weight alignment; both compact and padded rows.
    std::vector<Buffer*> weights;
    try {
        for (int j=0;j<nj;++j) {
            auto& m=mats[j];
            m.k=k; m.n=n;
            m.fmt=j==7 ? gg::kFmtBF16 : j%2 ? gg::kFmtGG : gg::kFmtQ8_0;
            m.gg_type=m.fmt==gg::kFmtGG ? 13 : 0; // actual Q5_K dense path
            const size_t row=m.fmt==gg::kFmtBF16 ? static_cast<size_t>(k)*2 :
                             m.fmt==gg::kFmtQ8_0 ? gg::q8_row_bytes(k) : gg::type_row_bytes(13,k);
            need(row>0,"weight geometry");
            const size_t stride=row+(m.fmt==gg::kFmtBF16 ? 16 : m.fmt==gg::kFmtQ8_0 ? 4 : 16);
            m.ld=m.fmt==gg::kFmtBF16 ? stride/2 : stride;
            std::vector<uint8_t> w(static_cast<size_t>(n)*stride,0x35);
            for (int r=0;r<n;++r) {
                uint8_t* wr=w.data()+static_cast<size_t>(r)*stride;
                if (m.fmt==gg::kFmtBF16) {
                    for(int i=0;i<k;++i) { wr[2*i]=0; wr[2*i+1]=0x3d; }
                } else if (m.fmt==gg::kFmtQ8_0) {
                    for(int b=0;b<k/32;++b) {
                        half_one(wr+34*b);
                        for(int i=0;i<32;++i) wr[34*b+2+i]=static_cast<uint8_t>((i*11+b+r)%127);
                    }
                } else {
                    for(int b=0;b<k/256;++b) {
                        uint8_t* block=wr+176*b;
                        half_one(block); half_one(block+2);
                        for(int i=4;i<176;++i) block[i]=static_cast<uint8_t>((i*13+b+r)%251);
                    }
                }
            }
            auto* bw=new Buffer(w.size()); weights.push_back(bw);
            ck(cudaMemcpy(bw->p,w.data(),w.size(),cudaMemcpyHostToDevice)); m.raw=bw->p;
            auto& job=jobs[j]; job.m=&m;
            const int which=j==5 || j==6 ? 1 : 0;
            job.xf=dx+static_cast<size_t>(which)*x.size();
            job.xf_cs=j==3 || j==4 ? ldx : static_cast<size_t>(k);
            job.ncol=j==4 ? 1 : nc;
            job.y=static_cast<float*>(output.p)+j*each+guard; job.y_cs=ys;
            job.bias=static_cast<float*>(dbias.p); job.alpha=0.75f;
        }
        for(int sharing=0;sharing<=1;++sharing) {
            ck(cudaMemcpy(output.p,init.data(),init.size()*sizeof(float),cudaMemcpyHostToDevice));
            gg::q8_share_test_mode(sharing);
            need(gg::mv(jobs,nj,stream),"mv refused");
            ck(cudaGetLastError()); ck(cudaStreamSynchronize(stream));
            int unique=-1,reused=-1; gg::q8_share_test_counts(unique,reused);
            const int expected_unique=nc==1 ? 2 : 4;
            need(unique==(sharing?expected_unique:7) && reused==(sharing?7-expected_unique:0),"effective sharing counts");
            auto& got=sharing?on:off;
            ck(cudaMemcpy(got.data(),output.p,got.size()*sizeof(float),cudaMemcpyDeviceToHost));
            for(int j=0;j<nj;++j) for(size_t z=0;z<each;++z) {
                const bool value=z>=guard && z<guard+static_cast<size_t>(jobs[j].ncol)*ys && (z-guard)%ys<static_cast<size_t>(n);
                const float v=got[j*each+z];
                need(value ? std::isfinite(v) && v!=sentinel : v==sentinel,"output finite/written/guard");
            }
        }
        need(std::memcmp(off.data(),on.data(),off.size()*sizeof(float))==0,"full GEMV output bytes differ");
        need(gg::launch_errors()==0,"GGUF launch errors");
    } catch (...) { for(auto* w:weights) delete w; throw; }
    for(auto* w:weights) delete w;
}

int main(int argc,char** argv) {
    if(argc!=3 || std::strcmp(argv[1],"--q8-share-check")!=0 || p::check_device(argv[2])<0 ||
       !p::required_flag(std::getenv("STRATA_DS4_Q8_BATCH"),std::getenv("DS4_Q8_BATCH")) ||
       !p::required_flag(std::getenv("STRATA_DS4_Q8_CHECK"),std::getenv("DS4_Q8_CHECK"))) {
        std::fprintf(stderr,"usage: --q8-share-check 0|1; Q8_BATCH=1 Q8_CHECK=1 required\n"); return 2;
    }
    cudaStream_t stream=nullptr;
    try {
        const int dev=p::check_device(argv[2]); ck(cudaSetDevice(dev));
        int major=0,minor=0; ck(cudaDeviceGetAttribute(&major,cudaDevAttrComputeCapabilityMajor,dev));
        ck(cudaDeviceGetAttribute(&minor,cudaDevAttrComputeCapabilityMinor,dev));
        need(major==8 && minor==0,"fixture requires selected SM80");
        need(gg::q8_batch(),"batch gate");
        std::string error;
        if (!gg::q8_batch_check(dev,error)) throw std::runtime_error(error);
        std::printf("PASS q8-reader-bytes-and-guards\n");
        ck(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
        int count=1;
        for(int k:{256,2304,5120,32768}) for(int nc:{1,2,4,8,16}) for(int n:{7,9}) for(int pattern:{0,1,2}) {
            one_case(k,nc,n,pattern,stream);
            std::printf("PASS mv-k%d-c%d-n%d-p%d\n",k,nc,n,pattern); ++count;
        }
        gg::q8_share_test_mode(-1);
        ck(cudaStreamDestroy(stream)); stream=nullptr;
        std::printf("ALL %d Q8_SHARE checks passed device %d\n",count,dev);
        return 0;
    } catch(const std::exception& e) {
        std::fprintf(stderr,"Q8_SHARE FAIL: %s\n",e.what());
        if(stream) cudaStreamDestroy(stream);
        return 1;
    }
}
