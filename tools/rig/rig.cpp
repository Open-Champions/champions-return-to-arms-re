// placeholder used for the first build of the core; replaced by the full runner
#include <cstdio>
#include "PS2VM.h"
#include "PS2VM_Preferences.h"
#include "AppConfig.h"
#include "gs/GSH_Null.h"

static fs::path g_basePath = "rig-data";
fs::path CAppConfig::GetBasePath() const
{
	return g_basePath;
}

int main(int argc, char** argv)
{
	printf("core links\n");
	return 0;
}
