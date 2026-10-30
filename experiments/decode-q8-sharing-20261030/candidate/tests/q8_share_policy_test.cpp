#include "../src/ds4/ds4_q8_share_policy.hpp"
#include <cstdio>
#include <stdexcept>
namespace p = strata::ds4::q8share;
static int checks = 0;
static void check(const char* id, bool ok) {
    if (!ok) { std::fprintf(stderr, "FAIL %s\n", id); throw std::runtime_error(id); }
    ++checks;
    std::printf("PASS %s\n", id);
}
int main() {
    try {
        int a[4]{}, b[4]{};
        const p::Key key{a, 256, 4, 256};
        check("identical_view", p::same_input(key, key));
        check("different_pointer", !p::same_input(key, {b,256,4,256}));
        check("different_stride", !p::same_input(key, {a,288,4,256}));
        check("different_rows", !p::same_input(key, {a,256,1,256}));
        check("different_k", !p::same_input(key, {a,256,4,32}));
        check("null_inputs", !p::same_input({nullptr,256,4,256}, {nullptr,256,4,256}));
        check("zero_rows", !p::same_input({a,256,0,256}, {a,256,0,256}));
        check("zero_k", !p::same_input({a,256,4,0}, {a,256,4,0}));
        check("negative_rows", !p::same_input({a,256,-1,256}, {a,256,-1,256}));
        check("negative_k", !p::same_input({a,256,4,-1}, {a,256,4,-1}));
        check("one_row_stride_normalized", p::effective_stride(1,999,256)==256);
        check("multirow_stride_preserved", p::effective_stride(4,288,256)==288);
        p::Key keys[8]{{b,256,4,256}, key, key, {a,288,4,256},
                      {a,256,1,256}, {a,256,4,32}, {b,288,4,256}, {a,512,16,512}};
        check("first_duplicate_wins", p::first_match(keys,8,key,true)==1);
        check("only_existing_prefix", p::first_match(keys,1,key,true)==-1);
        check("disabled_never_shares", p::first_match(keys,8,key,false)==-1);
        check("empty_plan", p::first_match(keys,0,key,true)==-1);
        check("negative_plan", p::first_match(keys,-1,key,true)==-1);
        check("over_capacity_plan", p::first_match(keys,9,key,true)==-1);
        check("null_plan", p::first_match(nullptr,1,key,true)==-1);
        check("last_entry", p::first_match(keys,8,keys[7],true)==7);
        check("first_entry", p::first_match(keys,8,keys[0],true)==0);
        check("nonmatching_plan", p::first_match(keys,8,{b,512,16,512},true)==-1);
        check("separate_call_no_reuse", p::first_match(keys,0,keys[7],true)==-1);
        check("default_off", !p::enabled(nullptr,nullptr));
        check("plain_one", p::enabled(nullptr,"1"));
        check("prefixed_one", p::enabled("1",nullptr));
        check("prefixed_zero_wins", !p::enabled("0","1"));
        check("prefixed_one_wins", p::enabled("1","0"));
        check("empty_off", !p::enabled("","1"));
        check("two_off", !p::enabled(nullptr,"2"));
        check("negative_off", !p::enabled(nullptr,"-1"));
        check("garbage_off", !p::enabled(nullptr,"1x"));
        check("whitespace_off", !p::enabled(nullptr," 1"));
        check("device_zero", p::check_device("0")==0);
        check("device_one", p::check_device("1")==1);
        check("device_null", p::check_device(nullptr)==-1);
        check("device_two", p::check_device("2")==-1);
        check("device_negative", p::check_device("-1")==-1);
        check("device_suffix", p::check_device("0x")==-1);
        check("device_multidigit", p::check_device("01")==-1);
        check("device_whitespace", p::check_device(" 0")==-1);
        check("required_unset", !p::required_flag(nullptr,nullptr));
        check("required_plain_one", p::required_flag(nullptr,"1"));
        check("required_prefixed_one", p::required_flag("1","0"));
        check("required_prefixed_zero", !p::required_flag("0","1"));
        check("required_malformed", !p::required_flag(nullptr,"1x"));
        std::printf("ALL %d Q8_SHARE policy checks passed\n", checks);
        return 0;
    } catch (const std::exception& e) { std::fprintf(stderr,"%s\n",e.what()); return 1; }
}
