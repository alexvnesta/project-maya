#include "../src/ds4/ds4_head_batch_policy.hpp"
#include <climits>
#include <cstdio>
#include <initializer_list>
#include <stdexcept>
#include <string>
namespace p = strata::ds4::head_batch;
static int checks = 0;
static void check(const std::string& id, bool ok) {
    if (!ok) throw std::runtime_error(id);
    ++checks; std::printf("PASS %s\n", id.c_str());
}
int main() {
    try {
        struct Env { const char* a; const char* b; int expected; };
        const Env env[] = {
            {nullptr,nullptr,4},{"0",nullptr,4},{nullptr,"0",4},{"0","0",4},
            {"1",nullptr,8},{nullptr,"1",8},{"1","1",8},{"1","0",-1},{"0","1",-1},
            {"",nullptr,-1},{"2",nullptr,-1},{"8",nullptr,-1},{"01",nullptr,-1},
            {" 1",nullptr,-1},{"1\n",nullptr,-1},{nullptr,"bad",-1},{"1","bad",-1}
        };
        for (int i=0;i<17;++i) check("env-"+std::to_string(i),p::width(env[i].a,env[i].b)==env[i].expected);
        const char* device[] = {nullptr,"0","1","2","-1","00","1x"," 0","0\n"};
        for (int i=0;i<9;++i) check("device-"+std::to_string(i),p::check_device(device[i])==(i==1?0:i==2?1:-1));
        for (int i=0;i<17;++i) {
            const bool expected=i==4 || i==5 || i==6;
            check("required-one-"+std::to_string(i),p::required_one(env[i].a,env[i].b)==expected);
        }
        for (int per:{4,8}) for (int rows=0;rows<=16;++rows) {
            int seen=0,calls=0; bool shape=true;
            const bool ok=p::each(rows,per,[&](int first,int count) {
                shape=shape && first==seen && count>0 && count<=per && count<=rows-first;
                seen+=count; ++calls; return true;
            });
            check("partition-p"+std::to_string(per)+"-r"+std::to_string(rows),ok && shape && seen==rows && calls==(rows+per-1)/per);
        }
        const int bad_rows[]={-1,17,INT_MIN,INT_MAX};
        for (int i=0;i<4;++i) {
            int calls=0;const bool ok=p::each(bad_rows[i],8,[&](int,int){++calls;return true;});
            check("bad-rows-"+std::to_string(i),!ok && calls==0);
        }
        const int bad_per[]={0,1,2,5,16,INT_MAX};
        for (int i=0;i<6;++i) {
            int calls=0;const bool ok=p::each(16,bad_per[i],[&](int,int){++calls;return true;});
            check("bad-width-"+std::to_string(i),!ok && calls==0);
        }
        for(int per:{4,8}) for(int fail:{1,2}) {
            int calls=0;const bool ok=p::each(16,per,[&](int,int){return ++calls!=fail;});
            check("stop-p"+std::to_string(per)+"-at"+std::to_string(fail),!ok && calls==fail);
        }
        std::printf("ALL %d HEAD_BATCH policy checks passed\n",checks); return 0;
    } catch(const std::exception& e) {std::fprintf(stderr,"HEAD_BATCH policy FAIL: %s\n",e.what());return 1;}
}
