#pragma once
#include <cstdint>
#include <cstring>
#include <stdexcept>
namespace health {
constexpr int K=5120,N=129280,G=16;
constexpr uint32_t guard=0x7fa12345u;
inline void require(bool x,const char* why) { if(!x) throw std::runtime_error(why); }
inline uint32_t bits(float x) {uint32_t v;std::memcpy(&v,&x,4);return v;}
// Q5_K d=1,dmin=0; eight scales=1; high bits=0; all codes=0,1 or2.
inline void block(uint8_t* b,int code) {
    require(code>=0 && code<=2,"code");std::memset(b,0,176);b[1]=0x3c;
    for(int i=0;i<4;++i) {b[4+i]=1;b[12+i]=1;}
    std::memset(b+48,code|(code<<4),128);
}
// Independent scalar unpacker, not a call into the selected GPU implementation.
inline int unpack(const uint8_t* b,int k) {
    require(k>=0 && k<256 && b[0]==0 && b[1]==0x3c && b[2]==0 && b[3]==0,"block header");
    int group=k/32,at=k%32;
    int scale=group<4?(b[4+group]&63):((b[8+group]&15)|((b[group]>>6)<<4));
    int mn=group<4?(b[8+group]&63):((b[8+group]>>4)|((b[4+group]>>6)<<4));
    require(mn==0,"minimum");
    int q=((b[48+(group/2)*32+at]>>(4*(group%2)))&15)|(((b[16+at]>>group)&1)<<4);
    return scale*q;
}
inline int code(int row,int pattern) {return pattern==0?0:1+row%2;}
inline int activation(int col) {return col%3==0?127:col%3==1?-127:0;}
inline float expected(int row,int col,int pattern) {return float(K*code(row,pattern)*activation(col));}
inline void host_check() {
    uint8_t b[176];
    for(int c=0;c<=2;++c) {block(b,c);for(int i=0;i<256;++i) require(unpack(b,i)==c,"independent Q5 decode");}
    require(expected(0,0,1)==650240 && expected(1,1,1)==-1300480 && expected(1,2,1)==0,"integer oracle");
}
}
