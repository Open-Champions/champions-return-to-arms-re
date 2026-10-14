// register.cpp - the extension's entry: RtaMachine, RtaAudioStream (and its playback), RtaDrawer.
#include "rta_audio.h"
#include "rta_drawer.h"
#ifdef RTA_GODOT_HAVE_GAMESTATE
#include "rta_gamestate.h"
#endif
#ifdef RTA_GODOT_HAVE_NET2
#include "rta_net2.h"
#endif
#include "rta_machine.h"

#include <gdextension_interface.h>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/defs.hpp>
#include <godot_cpp/godot.hpp>

using namespace godot;

static void initialize_rta_godot(ModuleInitializationLevel p_level) {
    if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) return;
    GDREGISTER_CLASS(RtaMachine);
    GDREGISTER_CLASS(RtaAudioPlayback);
    GDREGISTER_CLASS(RtaAudioStream);
    GDREGISTER_CLASS(RtaDrawer);
#ifdef RTA_GODOT_HAVE_GAMESTATE
    GDREGISTER_CLASS(RtaGameState);     // the HUD agent's: the game's state for a HUD drawn by Godot
#endif
#ifdef RTA_GODOT_HAVE_NET2
    GDREGISTER_CLASS(RtaNet2);          // the portal's: the online session (the game library's net2, or a mock-only copy)
#endif
}

static void uninitialize_rta_godot(ModuleInitializationLevel p_level) {
    if (p_level != MODULE_INITIALIZATION_LEVEL_SCENE) return;
}

extern "C" {
GDExtensionBool GDE_EXPORT rta_godot_init(GDExtensionInterfaceGetProcAddress p_get_proc_address, GDExtensionClassLibraryPtr p_library,
                                          GDExtensionInitialization* r_initialization) {
    godot::GDExtensionBinding::InitObject init_obj(p_get_proc_address, p_library, r_initialization);
    init_obj.register_initializer(initialize_rta_godot);
    init_obj.register_terminator(uninitialize_rta_godot);
    init_obj.set_minimum_library_initialization_level(MODULE_INITIALIZATION_LEVEL_SCENE);
    return init_obj.init();
}
}
