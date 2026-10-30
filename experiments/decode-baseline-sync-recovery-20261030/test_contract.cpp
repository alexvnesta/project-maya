#include "health_contract.hpp"
#include <cstdio>
#include <initializer_list>
int main() {
 health::host_check();
 int controls=0;uint8_t b[176];
 for(int c=0;c<3;++c) {health::block(b,c);for(int k=0;k<256;++k) health::require(health::unpack(b,k)==c,"decode");++controls;}
 for(int r:{0,1,129279}) for(int c:{0,1,2,3}) {health::require(health::expected(r,c,1)==float(5120*(1+r%2)*health::activation(c)),"oracle");++controls;}
 for(int invalid:{-1,3}) {bool fail=false;try{health::block(b,invalid);}catch(...){fail=true;}health::require(fail,"bad block accepted");++controls;}
 for(int invalid:{-1,256}) {bool fail=false;try{health::unpack(b,invalid);}catch(...){fail=true;}health::require(fail,"bad index accepted");++controls;}
 health::require(controls==19,"inventory");std::printf("ALL 19 HOST_CONTRACT controls passed\n");
}
