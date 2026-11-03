"""Additive mission-task lifetime model; the older quest API remains unchanged.

Observed/Executed contract: docs/spec/mission-unlocks.md, lifetime follow-up.
This models scheduled calls, not GPU timing or the subsequent world transition.
"""
import ref_quests as Q


class Menu:
    def __init__(self):
        self.fields = Q.new_menu()
        self.running = False
        self.chooser = 0

    def open(self, chooser):
        self.chooser = chooser
        self.fields.update(state=0, counter=0, mark=0, c0=0)
        self.running = True

    def remove(self):
        if self.fields['c0'] == 0:
            self.running = False

    def tick(self, button, world, network=False):
        if not self.running:
            return
        f = self.fields
        old = f['state']
        paused = f['paused']
        if old == 4:
            left = f['counter'] - 16
            if left >= 0:
                f['counter'] = left
            else:
                f.update(counter=0, paused=0)
                if f['c0']:
                    f['state'] = 5
                else:
                    self.running = False
        elif old == 6:
            if world.fade == 128:
                f['state'] = 7
            else:
                f['c0'] += 1
        else:
            Q.menu_tick(f, button, world)
            if old == 2:
                f['mark'] = min(f['mark'], 127)
            if old == 0 and network:
                f['paused'] = paused
            if old == 8:
                self.running = False

    def restore_request(self, level):
        # The bounded save_load body publishes a request, not a menu snapshot.
        self.fields.update(pending=level, orient=0xfd)
