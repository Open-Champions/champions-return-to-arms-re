// help_mac.mm - see help_host.h.
#include "help_host.h"
#include "fpcontrols.h"

#import <AppKit/AppKit.h>

namespace hosthelp {

std::string keys_text() {
    return "The game shows PlayStation buttons. On the keyboard they are:\n"
           "\n"
           "  Move (left stick)     W  A  S  D\n"
           "  Direction pad         the four arrow keys\n"
           "  Cross                 K          Circle      L\n"
           "  Square                J          Triangle    I\n"
           "  L1   Q                R1   E     L2   1      R2   3\n"
           "  L3   X                R3   C\n"
           "  Start (pause menu)    Return     Select      Backspace\n"
           "\n"
           "  Full screen           F or F11 (Escape leaves it)\n"
           "  Camera view           V (overhead, action, chase, shoulder, first person)\n"
           "  This list             F1\n"
           "\n"
           "A game controller that macOS knows (PlayStation, Xbox and others, by cable or\n"
           "Bluetooth) is player 1 as soon as it is connected - there is nothing to set up.\n"
           "It is listened to while this window is the one in front.\n"
           "\n"
           "To leave: close the window, or Command-Q. The game keeps your character only\n"
           "when it saves: at its own save points, and online by itself every few minutes.\n"
           "\n" + fpcontrols::help_text();
}

static NSPanel* g_panel = nil;

static NSWindow* game_window() {
    for (NSWindow* window in [NSApp windows])
        if ([window isVisible] && ![window isKindOfClass:[NSPanel class]]) return window;
    return nil;
}

static void make_panel() {
    if (g_panel) return;
    NSString* text = [NSString stringWithUTF8String:keys_text().c_str()];
    NSFont* font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightRegular];
    NSTextField* label = [NSTextField labelWithString:text];
    label.font = font;
    label.selectable = NO;
    [label sizeToFit];
    NSRect inner = NSMakeRect(16, 14, label.frame.size.width, label.frame.size.height);
    label.frame = inner;
    NSRect frame = NSMakeRect(0, 0, inner.size.width + 32, inner.size.height + 28);
    // a utility panel that does not become the key window: the keyboard stays the game's
    g_panel = [[NSPanel alloc] initWithContentRect:frame
                                         styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskUtilityWindow | NSWindowStyleMaskNonactivatingPanel)
                                           backing:NSBackingStoreBuffered defer:YES];
    g_panel.title = @"Keys and controller - Champions: Return to Arms";
    g_panel.releasedWhenClosed = NO;
    g_panel.becomesKeyOnlyIfNeeded = YES;
    g_panel.hidesOnDeactivate = YES;
    [g_panel.contentView addSubview:label];
}

static void show_now(bool toggle_it) {
    if (NSApp == nil) return;
    make_panel();
    if (toggle_it && [g_panel isVisible]) { [g_panel orderOut:nil]; return; }
    NSWindow* game = game_window();
    if (game) {
        // beside the game's window when there is room, else over its lower left corner
        NSRect g = game.frame, p = g_panel.frame, screen = game.screen ? game.screen.visibleFrame : g;
        CGFloat x = NSMaxX(g) + 12;
        if (x + p.size.width > NSMaxX(screen)) x = NSMinX(g) - p.size.width - 12;
        if (x < NSMinX(screen)) x = NSMinX(g) + 20;
        [g_panel setFrameOrigin:NSMakePoint(x, NSMaxY(g) - p.size.height)];
    }
    [g_panel orderFront:nil];
}

void show() { dispatch_async(dispatch_get_main_queue(), ^{ show_now(false); }); }
void toggle() { dispatch_async(dispatch_get_main_queue(), ^{ show_now(true); }); }

}  // namespace hosthelp

@interface RtaHelpMenu : NSObject
- (void)keys:(id)sender;
@end
@implementation RtaHelpMenu
- (void)keys:(id)sender { hosthelp::show_now(false); }
@end

namespace hosthelp {

static RtaHelpMenu* g_target = nil;

void start() {
    if (NSApp == nil || g_target) return;
    g_target = [[RtaHelpMenu alloc] init];
    NSMenu* bar = [NSApp mainMenu];
    if (!bar) { bar = [[NSMenu alloc] initWithTitle:@""]; [NSApp setMainMenu:bar]; }
    NSMenuItem* head = [[NSMenuItem alloc] initWithTitle:@"Help" action:nil keyEquivalent:@""];
    NSMenu* menu = [[NSMenu alloc] initWithTitle:@"Help"];
    NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:@"Keys and Controller" action:@selector(keys:) keyEquivalent:@""];
    item.target = g_target;
    [menu addItem:item];
    head.submenu = menu;
    [bar addItem:head];
}

void box(const std::string& headline, const std::string& text) {
    if (NSApp == nil) return;
    NSAlert* alert = [[NSAlert alloc] init];
    alert.messageText = [NSString stringWithUTF8String:headline.c_str()] ?: @"";
    alert.informativeText = [NSString stringWithUTF8String:text.c_str()] ?: @"";
    [alert addButtonWithTitle:@"OK"];
    [NSApp activateIgnoringOtherApps:YES];
    [alert runModal];
}

std::string test(const std::string& what) {
    __block std::string answer;
    void (^work)(void) = ^{
        if (what == "show") show_now(false);
        else if (what == "hide") { if (g_panel) [g_panel orderOut:nil]; }
        NSMenu* bar = NSApp ? [NSApp mainMenu] : nil;
        NSInteger at = bar ? [bar indexOfItemWithTitle:@"Help"] : -1;
        size_t lines = 1;
        for (char ch : keys_text()) if (ch == '\n') lines++;
        char text[256];
        snprintf(text, sizeof text, "help: panel made=%d up=%d size=%.0fx%.0f lines=%zu title=\"%s\"; Help menu in the bar=%d with %ld item(s)", g_panel != nil,
                 g_panel != nil && [g_panel isVisible], g_panel ? g_panel.frame.size.width : 0.0, g_panel ? g_panel.frame.size.height : 0.0, lines,
                 g_panel ? g_panel.title.UTF8String : "", at >= 0, at >= 0 ? (long)[[bar itemAtIndex:at].submenu numberOfItems] : 0L);
        answer = text;
    };
    if ([NSThread isMainThread]) work(); else dispatch_sync(dispatch_get_main_queue(), work);
    return answer;
}

}  // namespace hosthelp
