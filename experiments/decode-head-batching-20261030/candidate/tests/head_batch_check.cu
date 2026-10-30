// Finite standalone Q5_K head comparison. Original selected GGUF/IQ objects only.
// No model, benchmark, sampler, drafter setting, API or persistent state is used.
#include "ds4_gguf.cuh"
#include "../src/ds4/ds4_head_batch_policy.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <stdexcept>
#include <vector>
namespace gg = strata::ds4::gguf;
namespace p = strata::ds4::head_batch;
namespace x3 = strata::kernels::exl3;
static void ck(cudaError_t e) { if(e!=cudaSuccess) throw std::runtime_error(cudaGetErrorString(e)); }
static void need(bool ok,const char* why) { if(!ok) throw std::runtime_error(why); }
struct Buffer {
    void* ptr=nullptr;
    explicit Buffer(size_t bytes) { ck(cudaMalloc(&ptr,bytes)); }
    Buffer(const Buffer&)=delete;
    Buffer& operator=(const Buffer&)=delete;
    ~Buffer() { if(ptr) cudaFree(ptr); }
};
constexpr int K=5120, V=129280, GUARD=16;
constexpr uint32_t SENTINEL=0x7fa12345u; // Unwritten values cannot pass isfinite.
static uint32_t bits(float x) {uint32_t b;std::memcpy(&b,&x,4);return b;}

static void fill_weights(Buffer& device,int n,size_t stride) {
    // ggml Q5_K: finite FP16 d,dmin, 12 scale bytes, 32 high-bit bytes,
    // 128 packed quant bytes. Every scale/code bit pattern is legal.
    std::vector<uint8_t> w(static_cast<size_t>(n)*stride,0x5a);
    for(int row=0;row<n;++row) for(int block=0;block<K/256;++block) {
        uint8_t* b=w.data()+static_cast<size_t>(row)*stride+176*block;
        b[0]=0; b[1]=0x30; // +0.125 FP16
        b[2]=0; b[3]=0x2c; // +0.0625 FP16
        for(int i=4;i<176;++i) b[i]=static_cast<uint8_t>((row*7+block*19+i*13)%256);
    }
    ck(cudaMemcpy(device.ptr,w.data(),w.size(),cudaMemcpyHostToDevice));
    // The ~455MB host weight vector is released before any output vectors.
}

static void one_case(const x3::Mat& mat,int rows,int pattern,bool padded,cudaStream_t stream) {
    const size_t xs=K+(padded?32:0), ys=static_cast<size_t>(mat.n)+(padded?3:0);
    const size_t input_count=2*GUARD+static_cast<size_t>(rows)*xs;
    const size_t output_count=2*GUARD+static_cast<size_t>(rows)*ys;
    need(output_count<=2*GUARD+16ull*(V+3),"output allocation bound");
    std::vector<float> input(input_count,123.0f);
    for(int c=0;c<rows;++c) for(int k=0;k<K;++k) {
        const int v=(c*31+k*17)%251-125;
        float x=static_cast<float>(v)/127.0f;
        if(pattern==1) x=(k&1)?-0.0f:0.0f;
        if(pattern==2) x=k%4==0?1e-40f:k%4==1?-1e-40f:static_cast<float>(v)*1e8f;
        if(pattern==3) x=(k&1)?-1e-38f:1e-38f;
        input[GUARD+static_cast<size_t>(c)*xs+k]=x;
    }
    Buffer dx(input.size()*4),dy(output_count*4);
    ck(cudaMemcpy(dx.ptr,input.data(),input.size()*4,cudaMemcpyHostToDevice));
    std::vector<uint32_t> initial(output_count,SENTINEL);
    std::vector<float> off(output_count),on(output_count),input_after(input.size());
    int effective_eight=0;
    for(int per:{4,8}) {
        ck(cudaMemcpy(dy.ptr,initial.data(),output_count*4,cudaMemcpyHostToDevice));
        int calls=0,seen=0;
        const bool ok=p::each(rows,per,[&](int first,int count) {
            need(first==seen && count>0 && count<=per,"actual production-loop shape");
            seen+=count; ++calls;
            if(per==8 && count>4) ++effective_eight;
            x3::MvJob job{};job.m=&mat;job.ncol=count;
            job.xf=static_cast<float*>(dx.ptr)+GUARD+static_cast<size_t>(first)*xs;
            job.xf_cs=xs;
            job.y=static_cast<float*>(dy.ptr)+GUARD+static_cast<size_t>(first)*ys;
            job.y_cs=ys;job.alpha=1.0f;job.bias=nullptr;
            return gg::mv(&job,1,stream);
        });
        need(ok && seen==rows && calls==(rows+per-1)/per,"partition/mv refusal");
        ck(cudaGetLastError());ck(cudaStreamSynchronize(stream));
        auto& out=per==4?off:on;
        ck(cudaMemcpy(out.data(),dy.ptr,output_count*4,cudaMemcpyDeviceToHost));
        for(size_t i=0;i<output_count;++i) {
            const bool value=i>=GUARD && i<GUARD+static_cast<size_t>(rows)*ys &&
                             (i-GUARD)%ys<static_cast<size_t>(mat.n);
            need(value?std::isfinite(out[i]):bits(out[i])==SENTINEL,"finite outputs/canaries");
        }
        ck(cudaMemcpy(input_after.data(),dx.ptr,input.size()*4,cudaMemcpyDeviceToHost));
        need(std::memcmp(input.data(),input_after.data(),input.size()*4)==0,"input bytes/canaries changed");
        need(gg::launch_errors()==0,"GGUF launch error");
    }
    need(effective_eight==(rows>4?(rows/8+(rows%8>4)):0),"effective NC8 coverage");
    need(std::memcmp(off.data(),on.data(),output_count*4)==0,"exact F32 head outputs differ");
}

int main(int argc,char** argv) {
    if(argc!=3 || std::strcmp(argv[1],"--head-batch-check") || p::check_device(argv[2])<0 ||
       !p::required_one(std::getenv("STRATA_DS4_Q8_BATCH"),std::getenv("DS4_Q8_BATCH")) ||
       !p::required_one(std::getenv("STRATA_DS4_Q8_CHECK"),std::getenv("DS4_Q8_CHECK"))) {
        std::fprintf(stderr,"usage: --head-batch-check 0|1; Q8_BATCH=1 Q8_CHECK=1 required\n");return 2;
    }
    cudaStream_t stream=nullptr;
    try {
        const int dev=p::check_device(argv[2]);ck(cudaSetDevice(dev));
        int major=0,minor=0;ck(cudaDeviceGetAttribute(&major,cudaDevAttrComputeCapabilityMajor,dev));
        ck(cudaDeviceGetAttribute(&minor,cudaDevAttrComputeCapabilityMinor,dev));
        need(major==8 && minor==0,"selected SM80 required");
        need(gg::q8_batch(),"batch enabled required");std::string err;
        need(gg::q8_batch_check(dev,err),err.c_str());
        std::printf("PASS q8-reader-bytes-and-guards\n");
        ck(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));
        need(gg::prepare(stream),"selected GGUF scratch prepare");
        int count=1;
        for(int n:{7,9,V}) for(int padded:{0,1}) {
            const size_t row=gg::type_row_bytes(13,K);
            need(row==3520,"actual Q5_K row bytes");
            const size_t stride=row+(padded?16:0);
            need(static_cast<size_t>(n)*stride<=static_cast<size_t>(V)*3536,"weight allocation bound");
            Buffer weights(static_cast<size_t>(n)*stride);fill_weights(weights,n,stride);
            x3::Mat mat{};mat.fmt=gg::kFmtGG;mat.gg_type=13;mat.k=K;mat.n=n;
            mat.ld=static_cast<int>(stride);mat.raw=weights.ptr;
            for(int rows=1;rows<=16;++rows) for(int pattern=0;pattern<4;++pattern) {
                one_case(mat,rows,pattern,padded!=0,stream);
                std::printf("PASS head-k5120-n%d-pad%d-r%d-p%d\n",n,padded,rows,pattern);++count;
            }
        }
        ck(cudaStreamDestroy(stream));stream=nullptr;
        std::printf("ALL %d HEAD_BATCH checks passed device %d\n",count,dev);return 0;
    } catch(const std::exception& e) {
        std::fprintf(stderr,"HEAD_BATCH FAIL: %s\n",e.what());
        if(stream) cudaStreamDestroy(stream);return 1;
    }
}
