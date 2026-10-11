// See Rta.h.
#import <Foundation/Foundation.h>
#import <AppKit/AppKit.h>
#import <CoreVideo/CoreVideo.h>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <mutex>
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

void Rta::MakeBackgroundApplication()
{
	[NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
}

void Rta::SendWindowBack(void* nsView)
{
#if __has_feature(objc_arc)
	NSView* view = (__bridge NSView*)nsView;
#else
	NSView* view = (NSView*)nsView;
#endif
	[[view window] orderBack:nil];
}

// ---- the display's clock ---------------------------------------------------------------
// The machine makes 60 pictures a second and the display shows 60 or 120. Timed by a
// timer of its own, the machine drifts against the display: pictures reach the screen
// after one refresh, then after three, and movement stutters although nothing is slow.
// Here the display says when: a display link counts its refreshes, the machine starts
// each frame on a refresh (every second one at 120 Hz), and a finished picture is held
// back until the refresh before the one it is meant for, so that every picture stays
// on the screen for the same number of refreshes.

namespace
{
	std::mutex g_tickMutex;
	std::condition_variable g_tickCondition;
	uint64_t g_tick = 0;                 // refreshes counted
	std::atomic<double> g_refreshRate{0}; // per second; 0 until known
	std::atomic<bool> g_running{false};
	std::chrono::steady_clock::time_point g_lastTick;
	CVDisplayLinkRef g_displayLink = nullptr;

	// machine thread only
	uint64_t g_nextStart = 0;                // the refresh the next frame starts on
	std::atomic<uint64_t> g_frameStart{0};   // the refresh the current frame started on
	std::atomic<int> g_refreshesPerFrame{0}; // 0: the display is not pacing

	CVReturn OnRefresh(CVDisplayLinkRef, const CVTimeStamp*, const CVTimeStamp* outputTime, CVOptionFlags, CVOptionFlags*, void*)
	{
		if(outputTime && (outputTime->videoRefreshPeriod > 0))
		{
			g_refreshRate = static_cast<double>(outputTime->videoTimeScale) / static_cast<double>(outputTime->videoRefreshPeriod);
		}
		{
			std::lock_guard<std::mutex> lock(g_tickMutex);
			g_tick++;
			g_lastTick = std::chrono::steady_clock::now();
		}
		g_tickCondition.notify_all();
		return kCVReturnSuccess;
	}

	// waits for the count to reach 'tick'; false when the display link has stopped
	bool WaitForTick(uint64_t tick)
	{
		std::unique_lock<std::mutex> lock(g_tickMutex);
		while(g_tick < tick)
		{
			if(g_tickCondition.wait_for(lock, std::chrono::milliseconds(100)) == std::cv_status::timeout) return false;
		}
		return true;
	}
}

void Rta::StartDisplayClock()
{
	if(g_displayLink) return;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
	if(CVDisplayLinkCreateWithActiveCGDisplays(&g_displayLink) != kCVReturnSuccess || !g_displayLink) return;
	CVDisplayLinkSetOutputCallback(g_displayLink, &OnRefresh, nullptr);
	g_running = (CVDisplayLinkStart(g_displayLink) == kCVReturnSuccess);
#pragma clang diagnostic pop
}

double Rta::DisplayRefreshRate()
{
	return g_refreshRate;
}

int Rta::DisplayRefreshesPerFrame()
{
	return g_refreshesPerFrame;
}

// The frame limiter's wait: true when the display gave the start of the frame.
bool Rta::WaitForFrameStart(uint32_t framesPerSecond)
{
	double refreshRate = g_refreshRate;
	int perFrame = (framesPerSecond != 0) ? static_cast<int>(std::lround(refreshRate / framesPerSecond)) : 0;
	// only when the display's rate is the frame rate or a multiple of it (60 or 120 for
	// 60; within half a per cent, so 59.94 counts)
	if(!g_running || (perFrame < 1) || (std::fabs((refreshRate / perFrame) - framesPerSecond) > (framesPerSecond * 0.005)))
	{
		g_refreshesPerFrame = 0;
		g_nextStart = 0;
		return false;
	}
	uint64_t now;
	{
		std::lock_guard<std::mutex> lock(g_tickMutex);
		now = g_tick;
		// a display that has stopped refreshing (asleep) does not pace anything
		if((std::chrono::steady_clock::now() - g_lastTick) > std::chrono::milliseconds(200))
		{
			g_refreshesPerFrame = 0;
			g_nextStart = 0;
			return false;
		}
	}
	if((g_nextStart == 0) || (now >= (g_nextStart + perFrame)))
	{
		// the first frame, or more than a frame late: start from here
		g_nextStart = now + 1;
	}
	if(!WaitForTick(g_nextStart))
	{
		g_refreshesPerFrame = 0;
		g_nextStart = 0;
		return false;
	}
	g_frameStart = g_nextStart;
	g_nextStart += perFrame;
	g_refreshesPerFrame = perFrame;
	return true;
}

// The mark for a finished picture: the refresh before the one it is meant for. A frame
// that started on refresh s is meant for refresh s + perFrame; handed over after refresh
// s + perFrame - 1, it is shown then whether it took 3 ms to compute or 13.
uint64_t Rta::PresentMark()
{
	int perFrame = g_refreshesPerFrame;
	if(perFrame < 2) return 0;
	return g_frameStart + perFrame - 1;
}

void Rta::WaitForPresentMark(uint64_t mark)
{
	if(g_refreshesPerFrame < 2) return;
	WaitForTick(mark);
}
