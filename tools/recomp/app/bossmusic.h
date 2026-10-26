// bossmusic.h - the player's OWN music for boss fights, in the native program (the Godot
// version's tools/godot/project/hud/music/music.gd, done the same way here).
//
// Nothing is shipped and nothing is fetched.  The feature is a folder the player fills
// himself with audio files he owns: <data>/music/boss/ (.ogg, .mp3, .wav; another folder
// with "music.boss_dir").  With an empty or missing folder nothing changes at all.
//
// When a boss is engaged and there are tracks, the GAME's music is faded down and one of the
// player's tracks fades in (1.6 s), shuffled - none again before all were played - and
// looped while the fight lasts.  Four seconds after the boss is dead, or every local player
// is, or the boss is left behind, it crosses back to the game's music over 3 s.
//
// "A boss is engaged" is read from the game's state exactly as music.gd reads it (the state
// reader app/gamestate.h, the one the Godot HUD uses): a level is up, nobody is loading and
// not every local player is dead, and either the game's own boss meter is up (boss_uid), or a
// boss (rank 2) that is hostile, alive and not inert is after a player, aimed at by one, or
// hurt.  In the souls-style combat mode (soulscombat.h) a lock-on on a boss counts as well.
//
// Purely local sound.  Nothing here writes into the game or calls it: the reader only reads
// main memory, at the vertical blank, while the game's thread stands still.  The player's
// track is added to the sound AFTER the sound chip has made its samples (sound/drivers.cpp,
// rta_sound_set_host_mix), and the game's music is turned down with the host gain of the
// stream driver's music stream (stream 2; apprt::set_music_volume, the same control as the
// "music_volume" setting).  Nothing goes over the network.  Files are decoded on a thread of
// their own: the game never waits for a file.
//
// Settings (lines of <data>/settings.txt, or --boss-music on|off, --boss-music-dir DIR,
// --boss-music-volume V; "app music ..." while it runs):
//   music.boss = auto             auto (the default): on when a Remastered mode is wanted (Hardcore,
//                                 combat.mode; aiming, combat.aim), off in Classic - boss music is a
//                                 Remastered feature (portal/edition.gd) | on | off
//   music.boss_dir =              the folder of tracks; empty: <data>/music/boss/
//   music.boss_volume = 0.8       0..1, the player's tracks
//   music.boss_engage = auto      a test aid: on (engaged whatever the game says), off (never), auto
#pragma once
#include <cstdint>
#include <string>

namespace bossmusic {

// The data folder (the one the memory cards are in): the default folder is <data>/music/boss.
void set_data_folder(const std::string& data);
// "music.boss", "music.boss_dir", "music.boss_volume"; false when the key is not one of these.
bool setting(const char* key, const char* value);
std::string settings_text();
// The volume of the game's own music the player asked for (the "music_volume" setting, 0..1).  The
// director turns it down from there while a track plays.  False when the program has no sound library.
bool game_music_volume(double volume);
// Once per vertical blank on the game's thread (the controller read), while the game stands still.
void blank(uint64_t frame);
// "app music info | on | off | volume V | dir PATH | rescan | say"
std::string command(const std::string& text);
std::string figures();

}  // namespace bossmusic
