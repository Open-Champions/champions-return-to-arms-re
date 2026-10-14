// clicmd.h - see clicmd.cpp.
#pragma once
#include "session.h"

#include <string>

// Carries out one command line and prints what it has to say on standard output.  `quit`
// is set by "quit", `wait` (seconds) by "wait N"; a caller that has no use for them ignores them.
void net2_cli_command(net2* n, const std::string& line, bool& quit, double& wait);
// One "EVENT ..." line.
void net2_cli_event(const net2_event& e);
