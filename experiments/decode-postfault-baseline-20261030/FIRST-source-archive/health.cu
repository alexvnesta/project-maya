// Distinct post-fault baseline health witness. Original GGUF/IQ objects only.
// No experimental head loop, candidate Model, model weights, sampler or API.
#include "ds4_gguf.cuh"
#include "health_contract.hpp"
#include <cstdio>
#include <cmath>
#include <string>
#include <vector>
namespace gg=strata::ds4::gguf;
namespace x3=strata::kernels::exl3;
using namespace health;
static void ck(cudaError_t e) {if(e!=cudaSuccess) throw std::runtime_error(cudaGetErrorString(e));}
struct Buffer {
 void* p=nullptr;
 explicit Buffer(size_t n) {ck(cudaMalloc(&p,n));}
 Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
 ~Buffer(){if(p) cudaFree(p);}
};
static void one(int rows,int pad,int pattern,cudaStream_t stream) {
 size_t ws=3520+16*pad,xs=K+32*pad,ys=N+3*pad;
 Buffer w(size_t(N)*ws),x((2*G+rows*xs)*4),y((2*G+rows*ys)*4);
 {
  std::vector<uint8_t> host(size_t(N)*ws,0x5a);
  for(int r=0;r<N;++r) for(int b=0;b<K/256;++b) block(host.data()+size_t(r)*ws+b*176,code(r,pattern));
  ck(cudaMemcpy(w.p,host.data(),host.size(),cudaMemcpyHostToDevice));
 }
 std::vector<float> input(2*G+rows*xs,123.f);
 for(int c=0;c<rows;++c) for(int k=0;k<K;++k) input[G+c*xs+k]=float(activation(c));
 std::vector<uint32_t> initial(2*G+rows*ys,guard),out(initial.size());
 ck(cudaMemcpy(x.p,input.data(),input.size()*4,cudaMemcpyHostToDevice));
 ck(cudaMemcpy(y.p,initial.data(),initial.size()*4,cudaMemcpyHostToDevice));
 x3::Mat m{};m.fmt=gg::kFmtGG;m.gg_type=13;m.k=K;m.n=N;m.ld=int(ws);m.raw=w.p;
 x3::MvJob j{};j.m=&m;j.xf=static_cast<float*>(x.p)+G;j.xf_cs=xs;
 j.y=static_cast<float*>(y.p)+G;j.y_cs=ys;j.ncol=rows;j.alpha=1;
 // One original selected dispatch, <=4 columns. No comparison or new loop.
 require(rows==1 || rows==2 || rows==4,"original column bound");
 require(gg::mv(&j,1,stream),"original mv refused");ck(cudaGetLastError());ck(cudaStreamSynchronize(stream));
 ck(cudaMemcpy(out.data(),y.p,out.size()*4,cudaMemcpyDeviceToHost));
 for(size_t i=0;i<out.size();++i) {
  bool value=i>=G && i<G+rows*ys && (i-G)%ys<size_t(N);
  float actual;std::memcpy(&actual,&out[i],4);
  float want=value?expected(int((i-G)%ys),int((i-G)/ys),pattern):0;
  if(value?(!std::isfinite(actual)||out[i]!=bits(want)):out[i]!=guard) {
   std::fprintf(stderr,"BASELINE_HEALTH_BAD kind=%s index=%zu row=%zu col=%zu actual=%08x expected=%08x rows=%d pad=%d pattern=%d\n",
    value?"value":"guard",i,value?(i-G)%ys:0,value?(i-G)/ys:0,out[i],value?bits(want):guard,rows,pad,pattern);
   throw std::runtime_error("baseline output mismatch");
  }
 }
 std::vector<float> after(input.size());ck(cudaMemcpy(after.data(),x.p,input.size()*4,cudaMemcpyDeviceToHost));
 require(std::memcmp(after.data(),input.data(),input.size()*4)==0,"input/canary bytes changed");
 require(gg::launch_errors()==0,"selected launch error");
 std::printf("PASS baseline-k5120-n129280-r%d-pad%d-pattern%d\n",rows,pad,pattern);std::fflush(stdout);
}
int main(int argc,char** argv) {
 if(argc==2 && std::strcmp(argv[1],"--host-only")==0) {host_check();std::puts("PASS independent-Q5-pack-and-integer-oracle");return 0;}
 if(argc!=3 || std::strcmp(argv[1],"--baseline-health") || (std::strcmp(argv[2],"0") && std::strcmp(argv[2],"1"))) return 2;
 cudaStream_t stream=nullptr;
 try {
  host_check();int d=argv[2][0]-'0';ck(cudaSetDevice(d));int major=0,minor=0;
  ck(cudaDeviceGetAttribute(&major,cudaDevAttrComputeCapabilityMajor,d));ck(cudaDeviceGetAttribute(&minor,cudaDevAttrComputeCapabilityMinor,d));
  require(major==8 && minor==0,"SM80 required");require(gg::q8_batch(),"selected Q8 batch required");
  std::string why;require(gg::q8_batch_check(d,why),why.c_str());
  ck(cudaStreamCreateWithFlags(&stream,cudaStreamNonBlocking));require(gg::prepare(stream),"selected scratch");
  for(int r:{1,2,4}) for(int pad:{0,1}) for(int p:{0,1}) one(r,pad,p,stream);
  ck(cudaStreamDestroy(stream));stream=nullptr;
  std::printf("ALL 12 BASELINE_HEALTH checks passed device %d\n",d);return 0;
 } catch(const std::exception& e) {std::fprintf(stderr,"BASELINE_HEALTH FAIL: %s\n",e.what());if(stream) cudaStreamDestroy(stream);return 1;}
}
