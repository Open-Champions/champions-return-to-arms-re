// iface.h - the runtime's boundary to the parts it does not contain.
//
// The translated game plus runtime.cpp, iop.cpp and sound_null.cpp is a complete headless
// machine.  Four things leave it: the picture, the sound, the network and the controller.
// Each has one interface here.  An application that wants a window, audio or sockets
// implements the interface, puts a pointer into rta::Hooks and calls rta::run() from its
// own main(); main_headless.cpp is the smallest such application (it sets none of them).
//
// Rules common to all four:
//  - Every callback is made while the runtime holds its one lock, on the host thread that
//    carries the guest thread running at that moment.  Calls never overlap, but the host
//    thread making them changes from call to call (each guest thread is a host thread).
//    A sink with thread affinity (a GPU context, an audio device) must queue what it gets.
//  - Pointers handed to a callback are valid only until it returns.
//  - A callback must not call back into translated code.
//
// docs/issues/native-recomp.md, sections "Renderer interface", "Sound interface",
// "Network interface" and "Controller interface", say what the game sends through each.
#pragma once
#include <cstddef>
#include <cstdint>

namespace rta {

// ---- (a) picture ----------------------------------------------------------------------
// Everything the game sends toward the Graphics Synthesizer, in the order it sends it.
struct VideoSink {
    virtual ~VideoSink() {}

    // One DMA transfer to VIF1 (channel 1) or VIF0 (channel 0), flattened to the stream of
    // 32-bit words the VIF receives: the source chain is followed (call/return stack, tag
    // interrupts), and when CHCR.TTE is set the upper two words of every DMA tag are in
    // the stream ahead of the tag's data, as on the hardware.  A VIF decoder must keep its
    // state from one call to the next: a transfer can stop at a tag with the interrupt
    // bit and the next one continues the list.
    virtual void vif1(const uint32_t* words, size_t count) { (void)words; (void)count; }
    virtual void vif0(const uint32_t* words, size_t count) { (void)words; (void)count; }

    // One DMA transfer to the GIF (channel 2, PATH3): whole quadwords, four words each,
    // DMA tags removed.  GIF packets are not split across calls by the runtime, but the
    // game is free to split them, so a decoder keeps its state here too.
    virtual void gif(const uint32_t* words, size_t count) { (void)words; (void)count; }

    // A store to a register of the GS, GIF or VIF:
    //   0x12000000-0x12001080  GS privileged (PMODE, SMODE2, DISPFB1/2, DISPLAY1/2,
    //                          BGCOLOR, CSR, IMR, BUSDIR), 64 bits
    //   0x10003000-0x10003cff  GIF_CTRL/MODE, VIF0/VIF1 STAT, FBRST, ERR, MARK, 32 bits
    // CSR and IMR are also acted on by the runtime (interrupts); the sink sees the raw value.
    virtual void reg(uint32_t address, uint64_t value) { (void)address; (void)value; }

    // Start of a vertical blank.  `field` is GS CSR.FIELD after the flip (0 or 1),
    // `number` counts blanks since power-on.  A windowed application presents here, and
    // may block here: that is how it paces the game to the display.
    virtual void vblank(unsigned field, uint64_t number) { (void)field; (void)number; }

    // The game called gfx_dmaHandler(-1): a finished frame's eight lists of draw packets
    // (heads at 0x6f4070 + (buffer*8 + list)*4 in main memory, each a chain of nodes linked
    // through the word at +0xc) are about to be sent.  Return true to take the frame here: the
    // runtime then reports the frame as sent and no vif1()/gif() calls are made for it.
    // Return false (the default) and the game's own back end sends the lists through DMA.
    virtual bool frame(uint64_t number, unsigned buffer) { (void)number; (void)buffer; return false; }
};

// ---- (b) sound ------------------------------------------------------------------------
// The game reaches sound through two RPC servers on the I/O processor: the SDK's sound
// remote 0x80000701 (libsd calls: SPU2 registers, switches, addresses, voice transfers,
// effects) and its own stream driver 0x000163a5 (HELLO.IRX).  sound_null.cpp models both
// without producing sound - registers, the 2 MB of SPU2 memory, voice end flags and
// stream positions as functions of the virtual clock - and reports what a mixer needs.
struct SoundSink {
    virtual ~SoundSink() {}
    // sceSdSetParam / SetSwitch / SetAddr / SetCoreAttr as the game issued them: `entry`
    // is libsd's register selector (core in bit 0, voice in bits 1-5, register above),
    // `kind` 0 param, 1 switch, 2 address, 3 core attribute.
    virtual void spu_set(unsigned kind, uint32_t entry, uint32_t value) { (void)kind; (void)entry; (void)value; }
    // Bytes written into SPU2 memory (a sample upload, or half a stream buffer).
    virtual void spu_memory(uint32_t address, const uint8_t* data, uint32_t size) { (void)address; (void)data; (void)size; }
    // Once per vertical blank, after the model has advanced to `cycles` (CPU cycles of
    // the virtual clock, 294,912,000 per second).
    virtual void tick(uint64_t cycles) { (void)cycles; }
};

// ---- (c) network ----------------------------------------------------------------------
// The socket-level entries of Sony's libnet as the game's netcode calls them (addresses
// in docs/issues/native-recomp.md).  With no driver the entries answer as a console with
// no network adaptor does.  Values and errors are libnet's: >= 0 success, negative
// sceINETE_* codes; addresses are IPv4 in network byte order inside the 16-byte libnet
// address; `ms` is the time-out the game asked for (0 = do not wait, -1 = no limit).
struct NetAddress { uint8_t bytes[16]; };
struct NetDriver {
    virtual ~NetDriver() {}
    virtual int initialize() = 0;                                           // sceLibnetInitialize
    virtual int interface_list(int* ids, int max) = 0;                      // sceInetGetInterfaceList
    virtual int interface_control(int id, int code, void* data, int size) = 0;  // sceInetInterfaceControl
    // `param` is libnet's 0x40-byte sceInetParam (type, local port, remote address/port).
    virtual int create(const uint8_t* param) = 0;                           // sceInetCreate
    virtual int open(int cid, int ms) = 0;                                  // sceInetOpen
    virtual int close(int cid, int ms) = 0;                                 // sceInetClose
    virtual int send(int cid, const void* data, int size, int* flags, int ms) = 0;      // sceInetSend
    virtual int recv(int cid, void* data, int size, int* flags, int ms) = 0;            // sceInetRecv
    virtual int send_to(int cid, const void* data, int size, int* flags, const NetAddress& to, int port, int ms) = 0;
    virtual int recv_from(int cid, void* data, int size, int* flags, NetAddress* from, int* port, int ms) = 0;
    virtual int poll(void* pollfds, int count, int ms) = 0;                 // sceInetPoll
    virtual int name_to_address(int flags, NetAddress* out, const char* name, int ms, int retries) = 0;
    virtual int address_to_string(char* out, int size, const NetAddress& address) = 0;
};

// ---- (d) controller -------------------------------------------------------------------
// Buttons use libpad's bit values; 1 = held.  Sticks are 0-255 with 128 at rest.
enum PadButton : uint16_t {
    PAD_SELECT = 0x0001, PAD_L3 = 0x0002, PAD_R3 = 0x0004, PAD_START = 0x0008,
    PAD_UP = 0x0010, PAD_RIGHT = 0x0020, PAD_DOWN = 0x0040, PAD_LEFT = 0x0080,
    PAD_L2 = 0x0100, PAD_R2 = 0x0200, PAD_L1 = 0x0400, PAD_R1 = 0x0800,
    PAD_TRIANGLE = 0x1000, PAD_CIRCLE = 0x2000, PAD_CROSS = 0x4000, PAD_SQUARE = 0x8000,
};
struct PadState {
    uint16_t buttons = 0;
    uint8_t lx = 128, ly = 128, rx = 128, ry = 128;
};
struct PadSource {
    virtual ~PadSource() {}
    // Asked once per controller port (0, 1) at the start of every vertical blank, before
    // the game's blank handler runs; what it returns is what scePadRead gives the game
    // until the next blank.  `number` counts blanks since power-on.
    virtual void read(unsigned port, uint64_t number, PadState& state) = 0;
    // The game set the two vibration motors of a port (scePadSetActDirect).
    virtual void rumble(unsigned port, uint8_t small_motor, uint8_t large_motor) { (void)port; (void)small_motor; (void)large_motor; }
};

// ---- the machine ----------------------------------------------------------------------
struct Hooks {
    VideoSink* video = nullptr;
    SoundSink* sound = nullptr;
    NetDriver* net = nullptr;
    PadSource* pad = nullptr;       // overrides the script (--script) when set
};

// Runs the game; argv as for the headless program (see main_headless.cpp for the options).
// Does not return: the process ends when the run does.
int run(int argc, char** argv, const Hooks& hooks);

// Guest memory, for sinks that read what the game built: 32 MB of main memory, the 16 KB
// scratchpad (0x70000000), VU1's microprogram and data memories (0x11008000, 0x1100c000;
// stores the game makes there directly land here, VIF1 data is the sink's to apply).
uint8_t* memory();
uint8_t* scratchpad();
uint8_t* vu1_micro();
uint8_t* vu1_data();

}  // namespace rta
