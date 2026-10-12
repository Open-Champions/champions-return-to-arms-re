// stopgo <pid> <rate> [period_us]
// A stand-in for a slower computer: the process runs for period/rate and is stopped
// (SIGSTOP) for the rest of every period, so all of its threads get 1/rate of the time.
// Ends on SIGTERM/SIGINT (the process is continued first) or when the process is gone.
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>

static volatile sig_atomic_t g_end = 0;
static void onSignal(int s) { (void)s; g_end = 1; }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1e6 + t.tv_nsec / 1e3; }
static void until(double when)
{
	for(;;)
	{
		double left = when - now();
		if(left <= 0) return;
		if(left > 300) { struct timespec t = {0, (long)((left - 200) * 1000)}; nanosleep(&t, NULL); }
	}
}

int main(int argc, char** argv)
{
	if(argc < 3) { fprintf(stderr, "usage: stopgo <pid> <rate> [period_us]\n"); return 2; }
	pid_t pid = (pid_t)atoi(argv[1]);
	double rate = atof(argv[2]);
	double period = (argc > 3) ? atof(argv[3]) : 20000.0;
	if(rate <= 1.0 || pid <= 1) return 2;
	signal(SIGTERM, onSignal);
	signal(SIGINT, onSignal);
	double run = period / rate;
	double ran = 0, total = 0, start = now();
	// each phase lasts its length from when it really began: a late wake-up (a busy
	// computer) makes that phase longer, it is not taken out of the next one
	while(!g_end)
	{
		if(kill(pid, SIGCONT) != 0 && errno == ESRCH) break;
		double a = now();
		until(a + run);
		if(kill(pid, SIGSTOP) != 0 && errno == ESRCH) break;
		double b = now();
		ran += b - a;
		until(b + (period - run));
	}
	total = now() - start;
	kill(pid, SIGCONT);
	fprintf(stderr, "stopgo: the process ran %.1f %% of %.1f s (asked 1/%.1f = %.1f %%)\n", 100.0 * ran / total, total / 1e6, rate, 100.0 / rate);
	return 0;
}
