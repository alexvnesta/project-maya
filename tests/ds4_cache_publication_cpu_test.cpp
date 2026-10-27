// Runs the byte-exact production tick_flush method against a delayed-read CPU backend.
#include <array>
#include <cassert>
#include <condition_variable>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <mutex>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>
using cudaStream_t = int;
using cudaEvent_t = int;
using cudaError_t = int;
constexpr int cudaSuccess = 0;
struct Pending { const unsigned long long* pairs; int count; };
static std::array<std::vector<Pending>,2> pending;
static int sync_calls = 0, fail_sync = 0;
static volatile unsigned long long* guarded_input = nullptr;
static int cudaSetDevice(int) { return 0; }
static int cudaEventRecord(int,int) { return 0; }
static const char* cudaGetErrorString(int) { return "CPU injected predecessor failure"; }
static int cudaStreamSynchronize(int stream) {
    ++sync_calls;
    if (fail_sync) return 1;
    for(const auto& p:pending[(size_t)stream])for(int i=0;i<p.count;++i)
        *reinterpret_cast<unsigned long long*>(p.pairs[2*i]) = p.pairs[2*i+1];
    pending[(size_t)stream].clear();
    return 0;
}
static void tab_set(unsigned long long* p,int n,int stream) { pending[(size_t)stream].push_back({p,n}); }
struct TestImpl {
    struct Dev { int id,st; };
    struct RcJob { int slot; };
    static constexpr int kRcUpd=4;
    std::vector<Dev> devs{{0,0},{1,1}};
    std::vector<std::vector<unsigned long long>> tick_upd{2};
    std::vector<RcJob> tick_jobs;
    std::array<std::array<unsigned long long,8>,2> backing{};
    std::vector<unsigned long long*> rc_upd{backing[0].data(),backing[1].data()};
    std::vector<cudaEvent_t> rc_go{0,1};
    std::mutex rc_mu;
    std::condition_variable rc_cv;
    std::deque<RcJob> rc_q;
    bool buffers=true;
    bool tab_bufs() { return buffers; }
#include "native_tick_flush.inc"
};
static void reset() { for(auto& p:pending)p.clear();sync_calls=0;fail_sync=0; }
static unsigned long long addr(unsigned long long* p) { return reinterpret_cast<unsigned long long>(p); }
static void pass(const char* id) { std::printf("PASS %s\n",id); }
static void stop_on_abort(int) {
    // The real method must abort before overwriting the mapped input after a sync error.
    std::_Exit(guarded_input && guarded_input[0]==0x12345678ull ? 17 : 99);
}
int main() {
    {
        reset();TestImpl m;unsigned long long t[4]={1000,1001,1002,1003};
        m.tick_upd[0]={addr(t),0,addr(t+1),111};m.tick_flush();
        m.tick_upd[0]={addr(t+2),222,addr(t+3),333};m.tick_flush();
        assert(cudaStreamSynchronize(0)==0);
        assert(t[0]==0&&t[1]==111&&t[2]==222&&t[3]==333);pass("T01_actual_method_preserves_predecessor_pairs");
    }
    {
        reset();unsigned long long t[4]={1000,1001,1002,1003};unsigned long long p[4]={addr(t),0,addr(t+1),111};
        tab_set(p,2,0);p[0]=addr(t+2);p[1]=222;p[2]=addr(t+3);p[3]=333;tab_set(p,2,0);
        assert(cudaStreamSynchronize(0)==0);
        assert(t[0]==1000&&t[1]==1001&&t[2]==222&&t[3]==333);pass("T02_negative_control_unguarded_reuse_loses_pairs");
    }
    {
        reset();TestImpl m;m.tick_flush();assert(sync_calls==0);pass("T03_empty_tick_does_not_wait");
    }
    {
        reset();TestImpl m;m.tick_jobs={{7}};m.tick_flush();assert(m.rc_q.size()==1&&m.rc_q.front().slot==7&&sync_calls==0);
        pass("T04_jobs_without_input_overwrite_keep_queue_behavior");
    }
    {
        reset();TestImpl m;unsigned long long a=0,b=0;m.tick_upd[0]={addr(&a),21};m.tick_upd[1]={addr(&b),22};m.tick_flush();
        assert(cudaStreamSynchronize(0)==0&&cudaStreamSynchronize(1)==0);assert(a==21&&b==22);pass("T05_both_device_buffers_guarded");
    }
    {
        reset();TestImpl m;unsigned long long a=0;m.buffers=false;m.tick_upd[0]={addr(&a),21};m.tick_flush();
        assert(a==0&&sync_calls==0);pass("T06_buffer_refusal_does_not_publish");
    }
    {
        reset();assert(std::fflush(nullptr)==0);const pid_t pid=fork();assert(pid>=0);
        if(pid==0){TestImpl m;unsigned long long target=0;m.rc_upd[0][0]=0x12345678ull;guarded_input=m.rc_upd[0];fail_sync=1;
            std::signal(SIGABRT,stop_on_abort);m.tick_upd[0]={addr(&target),55};m.tick_flush();std::_Exit(98);}
        int status=0;assert(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==17);
        pass("T07_real_sync_error_aborts_before_mapped_overwrite");
    }
    std::puts("SUMMARY 7 controls PASS; CUDA/native/runtime UNRUN");
}
