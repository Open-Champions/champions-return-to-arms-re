// See Rta.h.
#import <Foundation/Foundation.h>
#include "Rta.h"

void Rta::KeepAwake()
{
	static id<NSObject> activity = nil;
	if(activity != nil) return;
	// Without this macOS "naps" an application whose window is covered: its timers are
	// stretched and its threads lose priority. In a lockstep game every other player
	// then waits for this machine.
	activity = [[NSProcessInfo processInfo]
	    beginActivityWithOptions:(NSActivityUserInitiated | NSActivityLatencyCritical)
	                      reason:@"an online game is running"];
#if !__has_feature(objc_arc)
	[activity retain];
#endif
}
