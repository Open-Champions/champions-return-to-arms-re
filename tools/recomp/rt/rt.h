// rt.h - what the parts of the runtime share with one another (not an interface for
// others: that is iface.h).
//
//   runtime.cpp     memory, clock, kernel, interrupts, DMA, hardware registers, run()
//   iop.cpp         the I/O processor's services behind sceSifBindRpc / sceSifCallRpc:
//                   module loader, disc drive, controller, multitap, memory card
//   sound_null.cpp  the two sound servers, modelled without output
//   script.cpp      scripted input, conditions and watches (the rig's script language)
//   main_headless.cpp  main()
#pragma once
#include "recomp.h"
#include "iface.h"

#include <functional>
#include <string>

// ---- runtime.cpp ------------------------------------------------------------------------
[[noreturn]] void rt_die(const char* format, ...);
void rt_note(const std::string& what);              // counted, printed in the final report
std::string rt_fmt(const char* format, ...);
extern bool g_rt_verbose;
extern rta::Hooks g_hooks;

static inline u32& W(u32 addr) { return *(u32*)(g_ram + addr); }
// a guest pointer as an index into main memory (kernel segments and mirrors folded), or
// ~0u when it does not point into it with `size` bytes to spare
static inline u32 guest_addr(u32 pointer, u32 size) {
    u32 a = pointer & 0x1FFFFFFF;
    return (a < RAM_SIZE && size <= RAM_SIZE - a) ? a : ~0u;
}

static const u64 CYCLES_PER_SECOND = 294912000ull;   // the virtual clock counts CPU cycles
static inline u64 usec_to_cycles(u64 usec) { return usec * CYCLES_PER_SECOND / 1000000ull; }
u64 rt_cycles();                                    // now
u64 rt_fields();                                    // vertical blanks since power-on

// Run `fn` when the clock has advanced by `delay` cycles, between two instructions of
// whatever guest thread runs then, with interrupts held (the context of an interrupt
// handler).  Used for answers of the I/O processor that arrive later.
void rt_after(u64 delay, std::function<void()> fn);
// From inside such a function: call a guest function as an interrupt handler is called.
void rt_call_handler(u32 address, u32 a0, u32 a1 = 0);
// Let the calling guest thread wait `delay` cycles of the clock (other threads and
// interrupts run meanwhile).  No-op in interrupt context.
void rt_sleep(Ctx* c, u64 delay);
// Kernel semaphore, from the runtime's side.
void rt_signal_sema(u32 id);

[[noreturn]] void rt_finish(int code);               // print the report and end the process
// Called once when the run ends, before the report is printed (an application's own
// figures, closing its window); set before rta::run().
extern void (*rt_at_finish)();
// "--opt key=value" on the command line, for modules linked with the runtime; nullptr when absent
const char* rt_option(const char* key);

// ---- iop.cpp ----------------------------------------------------------------------------
struct IopOptions {
    std::string disc;           // ISO 9660 image
    std::string card_root;      // directory holding mc0/ and mc1/ (Play!'s <data>/vfs)
    bool emulator_timing = false;   // answer after the delays the Play! emulator uses
};
void iop_init(const IopOptions& options);
void iop_vblank(u64 number);                        // controller buffers
u32 iop_sif_set_dma(u32 list, u32 count);           // system call 0x77: EE memory to IOP memory
u8* iop_ram();                                      // 2 MB
void iop_report();
// resume: take over the clients the image's game bound while it ran in the emulator
void iop_adopt();

// ---- sound_null.cpp ---------------------------------------------------------------------
// One RPC to a sound server.  Returns false for a server that is not a sound server.
bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size, u32 recv, u32 recv_size);
void sound_vblank();
void sound_report();

// ---- script.cpp -------------------------------------------------------------------------
void script_add_symbols(const char* path);          // "hex address <tab> name" lines
bool script_load(const char* path);
void script_add_command(const std::string& line);   // --do
void script_vblank(u64 number);                     // advances the script by one frame
bool script_active();                               // commands left
// The script command "app <text>" hands <text> to the application linked with the runtime
// (a window program: take a picture, press a key); `frame` is the script's frame number.
// Without a handler the command is noted and does nothing.  Set before rta::run().
extern void (*script_app_command)(const std::string& text, u64 frame);
const rta::PadState& script_pad(unsigned port);
// expressions and typed values, shared with the watch log
u32 script_eval(const std::string& expression);
std::string script_value(u32 address, const std::string& type);
