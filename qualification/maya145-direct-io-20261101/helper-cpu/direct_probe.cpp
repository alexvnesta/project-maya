// CPU-only controls around an exact generated slice of the frozen Maya header.
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <climits>
#include <vector>
#include <string>
#include <stdexcept>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <limits>
#include <utility>

static int inject=0, calls=0;
static bool alignment_ok=true;
static ssize_t observed_pread(int fd,void* p,size_t n,off_t off) {
    ++calls;
    alignment_ok &= (reinterpret_cast<uintptr_t>(p)%4096==0 && n%4096==0 && off%4096==0);
    if(inject==1) {errno=EINTR;return -1;}
    if(inject==2) {errno=EIO;return -1;}
    if(inject==3) return 0;
    return ::pread(fd,p,n,off);
}

// macOS tests the identical alignment/copy algorithm with buffered POSIX reads.
// It cannot qualify Linux O_DIRECT semantics. Linux uses the real flag below.
#if defined(__APPLE__)
#define O_DIRECT 0
#endif
using fd_t=intptr_t;
constexpr fd_t kBadFd=-1;
#define pread observed_pread
#include "exact_helpers.inc"
#undef pread

static void need(bool ok,const char* why) {if(!ok)throw std::runtime_error(why);}
static std::vector<uint8_t> bytes(size_t n) {
    std::vector<uint8_t> v(n);
    for(size_t i=0;i<n;++i)v[i]=uint8_t((i*137+(i>>7)*19)%251);
    return v;
}
static void same_inode(int a,int b) {
    struct stat x{},y{};
    need(fstat(a,&x)==0 && fstat(b,&y)==0,"fstat");
    need(x.st_dev==y.st_dev && x.st_ino==y.st_ino && x.st_size==y.st_size,"descriptor identity");
}
static void exact_copy(int fd,const std::vector<uint8_t>& original,uint64_t off,size_t n) {
    std::vector<uint8_t> out(n+34,0xa7),stage;
    alignment_ok=true;calls=0;
    need(copy_direct(fd,off,n,out.data()+17,stage),"direct copy refused");
    need(calls>0 && alignment_ok,"aligned read contract");
    need(std::equal(original.begin()+off,original.begin()+off+n,out.begin()+17),"source bytes");
    need(std::all_of(out.begin(),out.begin()+17,[](uint8_t x){return x==0xa7;}) &&
         std::all_of(out.end()-17,out.end(),[](uint8_t x){return x==0xa7;}),"destination canaries");
}
static void fallback(int fd,int buffered,uint64_t off,size_t n,const std::vector<uint8_t>& original) {
    std::vector<uint8_t> out(n+34,0xa7),stage;
    need(!copy_direct(fd,off,n,out.data()+17,stage),"expected direct failure");
    need(std::all_of(out.begin(),out.end(),[](uint8_t x){return x==0xa7;}),"failed copy wrote destination");
    // Same full-span buffered fallback as the frozen caller; no partial merge.
    need(::pread(buffered,out.data()+17,n,off)==ssize_t(n),"buffered fallback");
    need(std::equal(original.begin()+off,original.begin()+off+n,out.begin()+17),"fallback source bytes");
    need(out.front()==0xa7 && out.back()==0xa7,"fallback canaries");
}
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    const std::string id=argv[1],path=argv[2];
    int b=-1,d=-1;
    try {
        auto original=bytes(3*4096+733);
        int w=::open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);need(w>=0,"fresh fixture");
        need(::write(w,original.data(),original.size())==ssize_t(original.size()),"fixture write");
        need(::close(w)==0,"fixture close");
        b=::open(path.c_str(),O_RDONLY);d=open_direct(path);
        need(b>=0 && d>=0,"actual filesystem direct open required");same_inode(b,d);
#if defined(__linux__)
        need((fcntl(d,F_GETFL)&O_DIRECT)!=0,"actual Linux O_DIRECT absent");
#endif
        if(id=="aligned")exact_copy(d,original,4096,4096);
        else if(id=="unaligned")exact_copy(d,original,4099,4123);
        else if(id=="tiny")exact_copy(d,original,37,1);
        else if(id=="cross_page")exact_copy(d,original,4095,3);
        else if(id=="exact_eof")exact_copy(d,original,8193,original.size()-8193);
        else if(id=="numa_roles") {
            for(int r=0;r<3;++r)for(int x=0;x<2;++x)exact_copy(d,original,43+r*2048+x*1001,1001);
        } else if(id=="scratch_reuse") {
            std::vector<uint8_t> stage,out(5000);
            for(auto n:{size_t(17),size_t(5000),size_t(19)}) {
                need(copy_direct(d,31,n,out.data(),stage),"reuse");
                need(std::equal(out.begin(),out.begin()+n,original.begin()+31),"reuse bytes");
            }
        } else if(id=="truncated") {
            std::vector<uint8_t> stage,out(800,0xa7);
            need(!copy_direct(d,original.size()-100,800,out.data(),stage),"truncated wanted span");
            need(std::all_of(out.begin(),out.end(),[](uint8_t x){return x==0xa7;}),"truncated destination");
        } else if(id=="bad_fd_fallback")fallback(kBadFd,b,101,5001,original);
        else if(id=="eintr_fallback" || id=="ioerror_fallback" || id=="zero_fallback") {
            inject=id=="eintr_fallback"?1:id=="ioerror_fallback"?2:3;
            fallback(d,b,97,5001,original);need(calls==1,"error must not retry");
        } else if(id=="zero_and_overflow") {
            std::vector<uint8_t> stage,out(7,0xa7);
            for(auto pair:std::vector<std::pair<uint64_t,uint64_t>>{{0,0},{UINT64_MAX,2},{uint64_t(INT64_MAX)-4095,1},{0,uint64_t(INT64_MAX)}})
                need(!copy_direct(d,pair.first,pair.second,out.data(),stage),"invalid span accepted");
            need(stage.empty() && calls==0,"invalid span allocated/read");
            need(std::all_of(out.begin(),out.end(),[](uint8_t x){return x==0xa7;}),"invalid destination");
        } else if(id=="span_oracle") {
            for(uint64_t off=0;off<9000;off+=137)for(uint64_t n=1;n<9000;n+=211) {
                uint64_t lower=(off/4096)*4096,upper=((off+n+4095)/4096)*4096;
                need(direct_span(off,n)==upper-lower,"independent span oracle");
            }
        } else if(id=="identity_replacement") {
            std::string other=path+".replacement";
            int w2=::open(other.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600);need(w2>=0,"replacement create");
            need(::write(w2,original.data(),original.size())==ssize_t(original.size()),"replacement write");
            need(::close(w2)==0 && ::rename(other.c_str(),path.c_str())==0,"replace fixture only");
            int now=::open(path.c_str(),O_RDONLY);need(now>=0,"replacement open");
            struct stat old{},fresh{};need(fstat(d,&old)==0 && fstat(now,&fresh)==0,"replacement stats");
            need(old.st_ino!=fresh.st_ino || old.st_dev!=fresh.st_dev,"path identity must differ");
            need(::close(now)==0,"replacement close");same_inode(b,d);
        } else throw std::runtime_error("unknown control");
        need(::close(d)==0 && ::close(b)==0,"descriptor close");d=b=-1;
        need(::unlink(path.c_str())==0,"fixture cleanup");
        std::printf("PASS %s backend=%s\n",id.c_str(),
#if defined(__linux__)
          "linux-real-O_DIRECT"
#else
          "darwin-buffered-algorithm-only"
#endif
        );return 0;
    } catch(const std::exception& e) {
        if(d>=0)::close(d);
        if(b>=0)::close(b);
        ::unlink(path.c_str());
        std::fprintf(stderr,"FAIL %s %s\n",id.c_str(),e.what());return 1;
    }
}
