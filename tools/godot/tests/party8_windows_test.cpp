// Real party8 and translated load/store helpers with independently authored table contents.
#include "rt.h"
#include "party8.h"
#include "testerkit.h"
#include "../net2/hooks.h"
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

u8* g_ram = nullptr;
u32 g_reloc[PARTY8_TABLES] = {};
u32 g_reloc_spans[PARTY8_TABLES][2] = {{0x200000, 0x206000}, {0x300003, 0x300013}};
unsigned g_reloc_count = 2;
u32 g_party8_slots = 4;
const char* rt_option(const char*) { return nullptr; }
RecompFn rt_replace_function(u32, RecompFn) { return nullptr; }
u64 rt_load(u32, unsigned) { std::abort(); }
void rt_store(u32, unsigned, u64) { std::abort(); }
namespace testerkit { float text(render::FrameList&, float x, float, float, const std::string&, uint8_t, uint8_t, uint8_t, uint8_t) { return x; } }
static int checks = 0, failures = 0;
static void check(bool ok, const char* text) { ++checks; if (!ok) { ++failures; std::fprintf(stderr, "FAIL %s\n",text); } }
static u32 raw(u32 a) { u32 v; std::memcpy(&v,g_ram+a,4); return v; }
static uintptr_t unrelated_page = 0;
LONG CALLBACK recover_unrelated(EXCEPTION_POINTERS* fault) {
    const auto* r=fault->ExceptionRecord;
    if(r->ExceptionCode!=EXCEPTION_ACCESS_VIOLATION || r->NumberParameters<2 ||
       (uintptr_t)r->ExceptionInformation[1]!=unrelated_page) return EXCEPTION_CONTINUE_SEARCH;
    DWORD old; VirtualProtect((void*)unrelated_page,4096,PAGE_READWRITE,&old);
    std::puts("UNRELATED_HANDLER_REACHED");
    return EXCEPTION_CONTINUE_EXECUTION;
}
int main(int argc,char** argv) {
    g_ram=(u8*)std::calloc(RAM_SIZE+4096,1); if(!g_ram)return 2;
    g_party8_memtop=RAM_SIZE;
    const char* mode=argc>1?argv[1]:"normal";
    ST32(0x200004,0x12345678); ST32(0x03000000,0xaabbccdd);
    for(u32 k=0;k<16;++k)g_ram[0x300003+k]=(u8)(19+k);
    check(LD32(0x200004)==0x12345678 && !g_party8_delta,"disabled relocation reads original table");
    check(LD32(0x03000000)==0xaabbccdd && raw(0x01000000)==0,"upper 32 MB is independently addressable");
    const bool trap=std::strcmp(mode,"normal")!=0;
    if(trap)party8::command("on trap"); else party8::want(true,true);
    party8::blank(1);
    const u32 mapped=party8_at(0x200004);
    check(party8::moved() && mapped!=0x200004 && g_party8_delta==g_reloc,"production move publishes relocation map");
    check(LD32(0x200004)==0x12345678 && raw(mapped)==0x12345678,"dynamic translated load follows moved data");
    check((party8_at(0x300003)&15)==3,"moved unaligned table preserves low address bits");
    check(net2hook::party8_capable && net2hook::party8_capable()==1,"moved 64 MB copy can describe eight-player capability");
    ST32(0x200004,0x87654321);
    check(raw(mapped)==0x87654321,"dynamic translated store reaches moved table");
    net2hook::party8_game(8);
    check(g_party8_slots==8 && g_party8_wide==1,"room launch selects eight player-slot constants");
    net2hook::party8_game(0);
    check(g_party8_slots==4 && !g_party8_wide,"room stop restores four player-slot constants");
    if(!std::strcmp(mode,"trap")) {
        std::fflush(stdout);std::fflush(stderr);
        volatile u8 v=g_ram[0x201000];(void)v;
        std::puts("TRAP_WAS_MISSED");return 1;
    }
    if(!std::strcmp(mode,"unrelated")) {
        SYSTEM_INFO info;GetSystemInfo(&info);
        unrelated_page=((uintptr_t)(g_ram+0x400000)+info.dwPageSize-1)&~((uintptr_t)info.dwPageSize-1);
        AddVectoredExceptionHandler(0,recover_unrelated);
        DWORD old;VirtualProtect((void*)unrelated_page,info.dwPageSize,PAGE_NOACCESS,&old);
        volatile u8 v=*(volatile u8*)unrelated_page;(void)v;
        check(true,"unrelated access violation continued to the next handler");
    } else {
        check(raw(0x200004)==0xa5a5a5a5,"poison leaves stale original table visibly invalid");
        party8::want(false);party8::blank(2);
        check(!party8::moved() && !g_party8_delta && LD32(0x200004)==0x87654321,"move back restores modified contents and disables mapping");
    }
    std::printf("party8 Windows %s: %d checks, %d failures\n",mode,checks,failures);
    return failures?1:0;
}
