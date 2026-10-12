// rusage <pid>: instructions retired, processor cycles, user and system time (ns) of a
// process of the same user, as one line of JSON. Instructions and cycles do not depend on
// how busy the computer is the way times do.
#include <libproc.h>
#include <stdio.h>
#include <stdlib.h>
#include <mach/mach_time.h>

int main(int argc, char** argv)
{
	if(argc < 2) return 2;
	struct rusage_info_v4 info;
	if(proc_pid_rusage(atoi(argv[1]), RUSAGE_INFO_V4, (rusage_info_t*)&info) != 0) { perror("proc_pid_rusage"); return 1; }
	mach_timebase_info_data_t tb;
	mach_timebase_info(&tb);
	printf("{\"instructions\":%llu,\"cycles\":%llu,\"user_ns\":%llu,\"system_ns\":%llu}\n",
	       (unsigned long long)info.ri_instructions, (unsigned long long)info.ri_cycles,
	       (unsigned long long)(info.ri_user_time * tb.numer / tb.denom), (unsigned long long)(info.ri_system_time * tb.numer / tb.denom));
	return 0;
}
