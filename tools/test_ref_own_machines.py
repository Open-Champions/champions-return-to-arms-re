"""Synthetic locks for the ten own-machine run ticks. No ELF and no game bytes.

The tuples are the decision of ref_own_machines.step. difftest_own_machines.py
re-executes the same inputs on the original run functions.
"""
import unittest
import ref_own_machines as M

# name, state, ctx, requests, calls, stored words
LOCKED = [
    ('Gnaw', 0, {'seen': 1}, [3], ['v25', 'v27'], {}),
    ('Gnaw', 0, {}, [], ['v25', 'away'], {}),
    ('Gnaw', 0, {'away': 1}, [1], ['v25', 'away', 'v27'], {}),
    ('Gnaw', 1, {'seen': 1}, [3], ['v25', 'v27'], {}),
    ('Gnaw', 1, {}, [], ['v25', 'move_dest'], {}),
    ('Gnaw', 3, {}, [0], ['v27'], {}),
    ('Gnaw', 3, {'target': 1, 'see': 1}, [5], ['see', 'v27'], {}),
    ('Gnaw', 3, {'target': 1, 'seq': {'see': [0, 1]}}, [], ['see', 'see', 'turn'], {}),
    ('Gnaw', 3, {'target': 1, 'seq': {'see': [0, 0]}}, [], ['see', 'see', 'move_target'], {}),
    ('Gnaw', 5, {'target': 1, 'see': 1}, [6], ['see', 'v27'], {}),
    ('Gnaw', 5, {'target': 1, 'seq': {'see': [0, 1]}}, [], ['see', 'see', 'turn'], {}),
    ('Gnaw', 5, {'target': 1, 'seq': {'see': [0, 0]}}, [3], ['see', 'see', 'unroot', 'v27'], {}),
    ('Gnaw', 5, {'target': 1, 'rooted': 1, 'seq': {'see': [0, 0]}}, [], ['see', 'see', 'unroot'], {}),
    ('Gnaw', 6, {'target': 1, 'anim': 8}, [], ['turn'], {}),
    ('Gnaw', 6, {'target': 1, 'anim': 0, 'events': 1}, [5], ['turn', 'hit_arc', 'v27'], {}),
    ('Gnaw', 16, {'ready': 1}, [0], ['ready', 'v27'], {}),
    ('Gnaw', 16, {}, [], ['ready', 'flee'], {}),
    ('Gnaw', 18, {'anim': 16}, [], [], {}),
    ('Gnaw', 18, {}, [5], ['v27'], {}),
    ('Gnaw', 19, {}, [3], ['unstun', 'v27'], {}),
    ('Gnaw', 19, {'stunned': 1}, [], ['unstun'], {}),
    ('Gnaw', 20, {}, [], ['dead', 'delete'], {}),
    ('Gnaw', 7, {}, [0], ['v27'], {}),
    ('Skelight', 0, {'seen': 1}, [3], ['v25', 'v27'], {}),
    ('Skelight', 0, {'away': 1}, [1], ['v25', 'away', 'v27'], {}),
    ('Skelight', 0, {}, [], ['v25', 'away'], {}),
    ('Skelight', 1, {'seen': 1}, [3], ['v25', 'v27'], {}),
    ('Skelight', 1, {}, [], ['v25', 'move_dest'], {}),
    ('Skelight', 3, {}, [0], ['v27'], {}),
    ('Skelight', 3, {'target': 1, 'see': 1}, [6], ['see', 'v27'], {}),
    ('Skelight', 3, {'target': 1, 'seq': {'see': [0, 1]}}, [], ['see', 'see', 'turn'], {}),
    ('Skelight', 3, {'target': 1}, [], ['see', 'see', 'move_target'], {}),
    ('Skelight', 5, {'target': 1, 'see': 1}, [6], ['see', 'v27'], {}),
    ('Skelight', 5, {'target': 1}, [3], ['see', 'unroot', 'v27'], {}),
    ('Skelight', 5, {'target': 1, 'rooted': 1}, [], ['see', 'unroot'], {}),
    ('Skelight', 6, {'target': 1, 'anim': 8, 'timer': 5}, [], ['turn'], {244: 5}),
    ('Skelight', 6, {'target': 1, 'anim': 0, 'timer': 5, 'events': 1}, [], ['h17', 'hit_arc'], {244: 4}),
    ('Skelight', 6, {'target': 1, 'anim': 0, 'timer': 1, 'events': 1}, [3], ['h17', 'hit_arc', 'v27'], {244: 0}),
    ('Skelight', 6, {'anim': 0, 'timer': 5}, [], [], {244: 4}),
    ('Skelight', 6, {'anim': 8, 'timer': 0}, [3], ['v27'], {244: 0}),
    ('Skelight', 6, {'anim': 0, 'timer': 0}, [3], ['v27'], {244: 4294967295}),
    ('Skelight', 16, {'ready': 1}, [0], ['ready', 'v27'], {}),
    ('Skelight', 16, {}, [], ['ready', 'flee'], {}),
    ('Skelight', 18, {}, [3], ['v27'], {}),
    ('Skelight', 19, {}, [0], ['unstun', 'v27'], {}),
    ('Skelight', 19, {'stunned': 1}, [], ['unstun'], {}),
    ('Skelight', 20, {}, [], ['dead'], {}),
    ('Skelight', 23, {'anim': 128}, [0], ['v27', 'fx'], {}),
    ('Skelight', 23, {}, [], ['fx'], {}),
    ('Skelight', 7, {}, [], [], {}),
    ('GnomeNavigator', 0, {'cflags': 4194304, 'clock': 1000, 'timer': 0}, [1], ['v27'], {}),
    ('GnomeNavigator', 0, {'cflags': 8388608, 'away': 1, 'clock': 100, 'timer': 5000}, [1], ['away', 'v27'], {}),
    ('GnomeNavigator', 0, {'cflags': 12582912, 'away': 0, 'clock': 100, 'timer': 5000}, [], ['away'], {}),
    ('GnomeNavigator', 0, {'clock': 1000, 'timer': 0, 'away': 1}, [], [], {}),
    ('GnomeNavigator', 1, {'arrived': 1, 'clock': 100, 'timer': 5000}, [0], ['move_to', 'v27'], {}),
    ('GnomeNavigator', 1, {'arrived': 0, 'clock': 1000, 'timer': 0}, [0], ['move_to', 'v27'], {}),
    ('GnomeNavigator', 1, {'arrived': 0, 'clock': 100, 'timer': 5000}, [], ['move_to'], {}),
    ('GnomeNavigator', 3, {}, [0], ['v27'], {}),
    ('GnomeNavigator', 3, {'target': 1}, [], [], {}),
    ('GnomeNavigator', 5, {}, [3], ['unroot', 'v27'], {}),
    ('GnomeNavigator', 5, {'rooted': 1}, [], ['unroot'], {}),
    ('GnomeNavigator', 19, {}, [0], ['unstun', 'v27'], {}),
    ('GnomeNavigator', 19, {'stunned': 1}, [], ['unstun'], {}),
    ('GnomeNavigator', 20, {}, [], ['dead'], {}),
    ('GnomeNavigator', 6, {}, [], [], {}),
    ('GnomeNavigator', 18, {}, [], [], {}),
    ('Mermaid', 0, {'clock': 1000, 'timer': 0}, [1], ['move_by', 'v27'], {}),
    ('Mermaid', 0, {'clock': 100, 'timer': 5000}, [], ['move_by'], {}),
    ('Mermaid', 1, {'clock': 1000, 'timer': 0}, [0], ['move_by', 'v27'], {}),
    ('Mermaid', 1, {'clock': 100, 'timer': 5000, 'arrived': 1}, [], ['move_by', 'move_dest'], {}),
    ('Mermaid', 3, {}, [0], ['move_by', 'v27'], {}),
    ('Mermaid', 3, {'target': 1}, [], ['move_by'], {}),
    ('Mermaid', 5, {}, [3], ['move_by', 'unroot', 'v27'], {}),
    ('Mermaid', 5, {'rooted': 1}, [], ['move_by', 'unroot'], {}),
    ('Mermaid', 18, {'anim': 0}, [0], ['move_by', 'v27'], {}),
    ('Mermaid', 18, {'anim': 16}, [], ['move_by'], {}),
    ('Mermaid', 20, {'anim': 128}, [], ['move_by', 'stop'], {}),
    ('Mermaid', 20, {}, [], ['move_by'], {}),
    ('Mermaid', 19, {}, [], ['move_by'], {}),
    ('Mermaid', 2, {}, [], ['move_by'], {}),
    ('Natasla', 0, {}, [], [], {}),
    ('Natasla', 1, {'seen': 1, 'away': 1, 'target': 1}, [], [], {}),
    ('Natasla', 20, {}, [], [], {}),
    ('NPC', 0, {'cflags': 134217728}, [1], ['v27'], {}),
    ('NPC', 0, {}, [], [], {}),
    ('NPC', 1, {}, [], ['move_dest'], {}),
    ('NPC', 3, {'target': 1, 'seen': 1}, [], [], {}),
    ('Critter', 0, {'move': 1, 'clock': 1000, 'timer': 0}, [1], ['move_by', 'v27'], {}),
    ('Critter', 0, {'move': 1, 'clock': 100, 'timer': 5000}, [], ['move_by', 'away'], {}),
    ('Critter', 0, {'move': 1, 'clock': 1000, 'timer': 0, 'anim': 8}, [], ['move_by'], {}),
    ('Critter', 0, {'move': 1, 'away': 1, 'clock': 100, 'timer': 5000}, [1], ['move_by', 'away', 'v27'], {}),
    ('Critter', 0, {'clock': 1000, 'timer': 0}, [], ['move_by'], {}),
    ('Critter', 0, {'fidget_a': 1, 'move': 1, 'clock': 1000, 'fid_time': 0, 'timer': 5000}, [], ['move_by', 'anim_bio', 'rand'], {}),
    ('Critter', 0, {'fidget_a': 1, 'fidget_b': 1, 'move': 1, 'clock': 1000, 'fid_time': 0, 'timer': 5000, 'rand': 1}, [], ['move_by', 'rand', 'anim_bio', 'rand'], {}),
    ('Critter', 0, {'class_flags': 16, 'move': 1, 'clock': 1000, 'timer': 0}, [1], ['v27'], {}),
    ('Critter', 0, {'class_flags': 16, 'move': 1, 'clock': 100, 'timer': 5000}, [], ['away'], {}),
    ('Critter', 0, {'fidget_a': 1, 'move': 1, 'clock': 1000, 'fid_time': 0, 'timer': 0}, [], ['move_by', 'anim_bio', 'rand'], {}),
    ('Critter', 1, {'idle': 1, 'arrived': 1, 'clock': 100, 'timer': 5000}, [0], ['move_to', 'v27'], {}),
    ('Critter', 1, {'arrived': 1, 'clock': 100, 'timer': 5000}, [], ['move_to', 'clear_path', 'wander', 'rand'], {}),
    ('Critter', 1, {'idle': 1, 'clock': 1000, 'timer': 0}, [0], ['move_to', 'v27'], {}),
    ('Critter', 1, {'idle': 1, 'anim': 8, 'clock': 1000, 'timer': 0}, [0], ['move_to', 'v27'], {}),
    ('Critter', 1, {'class_flags': 2, 'arrived': 1, 'clock': 100, 'timer': 5000}, [], ['move_direct', 'clear_path', 'wander', 'rand'], {}),
    ('Critter', 1, {'idle': 1, 'class_flags': 8, 'arrived': 1, 'clock': 100, 'timer': 5000}, [], ['move_to', 'clear_path', 'wander', 'rand'], {}),
    ('Critter', 1, {'idle': 1, 'class_flags': 8, 'clock': 1000, 'timer': 0}, [0], ['move_to', 'v27'], {}),
    ('Critter', 1, {'idle': 1, 'clock': 100, 'timer': 5000}, [], ['move_to'], {}),
    ('Critter', 1, {'class_flags': 16, 'idle': 1, 'clock': 1000, 'timer': 0}, [0], ['v27'], {}),
    ('Critter', 16, {'idle': 1}, [0], ['v27'], {}),
    ('Critter', 16, {}, [1], ['v27'], {}),
    ('Critter', 16, {'target': 1, 'flee_clip': 1, 'clock': 100, 'timer': 5000}, [], ['flee_from'], {}),
    ('Critter', 16, {'target': 1, 'flee_clip': 1, 'idle': 1, 'clock': 1000, 'timer': 0}, [0], ['flee_from', 'handle_clear', 'v27'], {}),
    ('Critter', 20, {}, [], ['stop', 'v28'], {}),
    ('Critter', 22, {'path': 1}, [], ['path', 'approach'], {}),
    ('Critter', 22, {}, [], ['path'], {}),
    ('Critter', 22, {'path': 1, 'snap': 1}, [], ['path'], {}),
    ('Critter', 23, {'fidget_a': 1, 'clock': 1000, 'fid_time': 0}, [], ['anim_bio', 'rand'], {}),
    ('Critter', 7, {}, [], [], {}),
    ('AntQueen', 0, {'seen': 1, 'queue': 1, 'clock': 100, 'timer': 5000}, [3], ['aq_ground', 'v25', 'v27'], {}),
    ('AntQueen', 0, {'seen': 0, 'queue': 1, 'clock': 100, 'timer': 5000}, [], ['aq_ground', 'v25', 'v25'], {}),
    ('AntQueen', 0, {'queue': 1, 'clock': 100, 'timer': 5000, 'seq': {'v25': [0, 1]}}, [3], ['aq_ground', 'v25', 'v25', 'v27'], {}),
    ('AntQueen', 0, {'seen': 1, 'queue': 4, 'clock': 100, 'timer': 5000}, [], ['aq_ground', 'v25', 'v25'], {}),
    ('AntQueen', 0, {'seen': 0, 'queue': 4, 'clock': 1000, 'timer': 0}, [1], ['aq_ground', 'v25', 'v25', 'v27'], {}),
    ('AntQueen', 1, {'seen': 1}, [3], ['aq_air', 'v25', 'v27'], {}),
    ('AntQueen', 1, {}, [], ['aq_air', 'v25', 'move_dest'], {}),
    ('AntQueen', 3, {}, [0], ['aq_air', 'v27'], {}),
    ('AntQueen', 3, {'target': 1, 'rand': 0, 'enemy': 1, 'flight': 5000, 'clock': 100}, [7], ['aq_air', 'rand', 'enemy', 'v27'], {}),
    ('AntQueen', 3, {'target': 1, 'rand': 0, 'enemy': 0, 'flight': 5000, 'clock': 100}, [], ['aq_air', 'rand', 'enemy', 'move_target'], {}),
    ('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 1, 'flight': 5000, 'clock': 100}, [6], ['aq_air', 'rand', 'see', 'v27'], {}),
    ('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 0, 'flight': 5000, 'clock': 100}, [], ['aq_air', 'rand', 'see', 'move_target'], {}),
    ('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 0, 'flight': 0, 'clock': 1000, 'queue': 1}, [8], ['aq_air', 'rand', 'see', 'move_target', 'v27'], {}),
    ('AntQueen', 3, {'target': 1, 'rand': 1, 'see': 0, 'flight': 0, 'clock': 1000, 'queue': 4}, [], ['aq_air', 'rand', 'see', 'move_target'], {}),
    ('AntQueen', 5, {'target': 1, 'rand': 0, 'enemy': 1}, [7], ['rand', 'enemy', 'v27'], {}),
    ('AntQueen', 5, {'target': 1, 'rand': 1, 'see': 1}, [6], ['rand', 'see', 'v27'], {}),
    ('AntQueen', 5, {'rand': 1, 'see': 0}, [3], ['rand', 'unroot', 'v27'], {}),
    ('AntQueen', 5, {'rand': 1, 'see': 0, 'rooted': 1}, [], ['rand', 'unroot'], {}),
    ('AntQueen', 5, {'rand': 0, 'enemy': 0}, [3], ['rand', 'unroot', 'v27'], {}),
    ('AntQueen', 5, {'target': 1, 'rand': 0, 'enemy': 0}, [3], ['rand', 'enemy', 'unroot', 'v27'], {}),
    ('AntQueen', 6, {'target': 1, 'anim': 8, 'events': 0}, [], ['aq_ground', 'turn'], {}),
    ('AntQueen', 6, {'target': 1, 'anim': 8, 'events': 1}, [], ['aq_ground', 'hit_reach'], {}),
    ('AntQueen', 6, {'target': 1, 'anim': 0}, [3], ['aq_ground', 'turn', 'v27'], {}),
    ('AntQueen', 7, {'anim': 8, 'events': 1}, [], ['aq_ground', '000000', 'hit_or'], {}),
    ('AntQueen', 7, {'anim': 0}, [3], ['aq_ground', 'v27'], {}),
    ('AntQueen', 7, {'anim': 0, 'events': 1}, [3], ['aq_ground', '000000', 'hit_or', 'v27'], {}),
    ('AntQueen', 8, {'flight': 5000, 'clock': 100}, [0], ['aq_air', 'v27'], {980: 5000}),
    ('AntQueen', 8, {'target': 1, 'anim': 8, 'flight': 5000, 'clock': 100}, [], ['aq_air'], {980: 5000}),
    ('AntQueen', 8, {'target': 1, 'anim': 0, 'see': 1, 'flight': 5000, 'clock': 100, 'rand': 0}, [9], ['aq_air', 'see', 'v27', 'rand'], {980: 0}),
    ('AntQueen', 8, {'target': 1, 'anim': 0, 'see': 1, 'flight': 5000, 'clock': 100, 'rand': 1}, [9], ['aq_air', 'see', 'v27', 'rand'], {980: 5000}),
    ('AntQueen', 8, {'target': 1, 'anim': 0, 'see': 0, 'flight': 5000, 'clock': 100}, [], ['aq_air', 'see', 'see', 'move_target'], {980: 5000}),
    ('AntQueen', 8, {'target': 1, 'anim': 0, 'flight': 0, 'clock': 1000}, [23], ['aq_air', 'v27'], {980: 0}),
    ('AntQueen', 9, {'target': 1, 'anim': 8, 'events': 1}, [], ['aq_ground', '000000', 'hit_reach', 'turn'], {}),
    ('AntQueen', 9, {'target': 1, 'anim': 0}, [8], ['aq_ground', 'turn', 'v27'], {}),
    ('AntQueen', 10, {'target': 1, 'anim': 0, 'events': 1}, [23], ['aq_ground', '000000', 'hit_reach', 'turn', 'v27'], {}),
    ('AntQueen', 10, {'target': 1, 'anim': 8}, [], ['aq_ground', 'turn'], {}),
    ('AntQueen', 18, {'anim': 16}, [], ['aq_ground'], {}),
    ('AntQueen', 18, {'anim': 0, 'queue': 1}, [3], ['aq_ground', 'v27'], {}),
    ('AntQueen', 18, {'anim': 0, 'queue': 4}, [], ['aq_ground'], {}),
    ('AntQueen', 19, {}, [0], ['unstun', 'v27'], {}),
    ('AntQueen', 19, {'stunned': 1}, [], ['unstun'], {}),
    ('AntQueen', 20, {}, [], ['aq_ground', 'dead'], {}),
    ('AntQueen', 23, {}, [0], ['aq_air', 'v27'], {980: 0}),
    ('AntQueen', 23, {'target': 1, 'anim': 8, 'flight': 5000, 'clock': 100}, [], ['aq_air'], {980: 5000}),
    ('AntQueen', 23, {'target': 1, 'anim': 0, 'flight': 5000, 'clock': 100}, [], ['aq_air', 'move_to'], {980: 5000}),
    ('AntQueen', 23, {'target': 1, 'anim': 0, 'flight': 5000, 'clock': 100, 'arrived': 1}, [], ['aq_air', 'move_to'], {980: 0}),
    ('AntQueen', 23, {'target': 1, 'anim': 0, 'flight': 5000, 'clock': 100, 'stuck': 31}, [], ['aq_air', 'move_to'], {980: 0}),
    ('AntQueen', 23, {'target': 1, 'anim': 0, 'flight': 5000, 'clock': 100, 'stuck': 30}, [], ['aq_air', 'move_to'], {980: 5000}),
    ('AntQueen', 23, {'target': 1, 'anim': 0, 'flight': 0, 'clock': 1000, 'see': 1}, [24], ['aq_air', 'turn', 'see', 'v27'], {980: 0}),
    ('AntQueen', 23, {'target': 1, 'anim': 0, 'flight': 0, 'clock': 1000, 'see': 0}, [], ['aq_air', 'turn', 'see'], {980: 0}),
    ('AntQueen', 24, {'anim': 8}, [], ['aq_ground'], {}),
    ('AntQueen', 24, {'anim': 0, 'queue': 1}, [3], ['aq_ground', 'v27'], {}),
    ('AntQueen', 24, {'anim': 0, 'queue': 4}, [], ['aq_ground'], {}),
    ('AntQueen', 25, {'target': 1, 'clock': 1000, 'timer': 1120, 'queue': 1}, [], ['aq_ground', 'cos16', 'sin16', 'pool'], {}),
    ('AntQueen', 25, {'target': 1, 'clock': 1000, 'timer': 0, 'queue': 1}, [3], ['aq_ground', 'v27'], {}),
    ('AntQueen', 25, {'target': 1, 'clock': 100, 'timer': 5000, 'queue': 1}, [], ['aq_ground'], {}),
    ('AntQueen', 16, {}, [], [], {}),
    ('AntQueen', 2, {}, [], [], {}),
    ('Skeleton', 0, {'seen': 1, 'clock': 100, 'timer': 5000}, [3], ['v25', 'v27'], {}),
    ('Skeleton', 0, {'clock': 100, 'timer': 5000}, [], ['v25', 'away'], {}),
    ('Skeleton', 0, {'away': 1, 'clock': 100, 'timer': 5000}, [1], ['v25', 'away', 'v27'], {}),
    ('Skeleton', 0, {'clock': 1000, 'timer': 0}, [1], ['v25', 'v27'], {}),
    ('Skeleton', 0, {'kind': 4, 'seen': 1, 'clock': 100, 'timer': 5000}, [3], ['v25', 'v27'], {}),
    ('Skeleton', 0, {'kind': 4, 'clock': 100, 'timer': 5000}, [], ['v25', 'v25', 'away'], {}),
    ('Skeleton', 0, {'kind': 4, 'seq': {'v25': [0, 1]}, 'clock': 100, 'timer': 5000}, [3], ['v25', 'v25', 'v27'], {}),
    ('Skeleton', 1, {'seen': 1}, [3], ['v25', 'v27'], {}),
    ('Skeleton', 1, {'clock': 1000, 'timer': 0}, [0], ['v25', 'v27'], {}),
    ('Skeleton', 1, {'clock': 100, 'timer': 5000}, [], ['v25', 'move_dest'], {}),
    ('Skeleton', 1, {'kind': 4, 'clock': 100, 'timer': 5000}, [], ['v25', 'v25', 'move_dest'], {}),
    ('Skeleton', 3, {}, [0], ['v27'], {}),
    ('Skeleton', 3, {'target': 1, 'see': 1}, [6], ['see', 'v27'], {}),
    ('Skeleton', 3, {'target': 1, 'seq': {'see': [0, 1]}}, [], ['see', 'ally', 'see', 'turn'], {}),
    ('Skeleton', 3, {'target': 1, 'ally': 1, 'rand': 7}, [5], ['see', 'ally', 'rand', 'v27'], {}),
    ('Skeleton', 3, {'target': 1}, [], ['see', 'ally', 'see', 'move_target'], {}),
    ('Skeleton', 3, {'kind': 4, 'target': 1, 'see': 1}, [8], ['see', 'v27'], {}),
    ('Skeleton', 3, {'kind': 4, 'target': 1, 'seq': {'see': [0, 1]}}, [], ['see', 'see', 'turn'], {}),
    ('Skeleton', 3, {'kind': 4, 'target': 1}, [], ['see', 'see', 'move_target'], {}),
    ('Skeleton', 5, {'target': 1, 'see': 1}, [6], ['see', 'v27'], {}),
    ('Skeleton', 5, {'target': 1, 'clock': 1000, 'timer': 0}, [3], ['see', 'unroot', 'v27'], {}),
    ('Skeleton', 5, {'target': 1, 'clock': 100, 'timer': 5000, 'ally': 1}, [], ['see', 'unroot', 'ally'], {}),
    ('Skeleton', 5, {'target': 1, 'clock': 100, 'timer': 5000, 'ally': 0}, [3], ['see', 'unroot', 'ally', 'v27'], {}),
    ('Skeleton', 5, {'clock': 100, 'timer': 5000}, [], ['see', 'unroot'], {}),
    ('Skeleton', 5, {'target': 1, 'rooted': 1, 'clock': 1000, 'timer': 0}, [], ['see', 'unroot'], {}),
    ('Skeleton', 5, {'kind': 4, 'target': 1, 'see': 1}, [8], ['see', 'v27'], {}),
    ('Skeleton', 6, {'target': 1, 'anim': 8, 'timer': 5}, [], ['turn'], {244: 5}),
    ('Skeleton', 6, {'target': 1, 'anim': 0, 'timer': 5, 'events': 1}, [], ['h17', 'hit_reach'], {244: 4}),
    ('Skeleton', 6, {'target': 1, 'anim': 0, 'timer': 1, 'events': 1}, [3], ['h17', 'hit_reach', 'v27'], {244: 0}),
    ('Skeleton', 6, {'target': 1, 'anim': 8, 'timer': 1, 'events': 1}, [], ['h17', 'hit_reach', 'turn'], {244: 1}),
    ('Skeleton', 8, {'anim': 8, 'timer': 5}, [0], ['v27'], {244: 5}),
    ('Skeleton', 8, {'anim': 0, 'timer': 5}, [0], ['v27'], {244: 4}),
    ('Skeleton', 8, {'anim': 0, 'timer': 1}, [0, 3], ['v27', 'v27'], {244: 0}),
    ('Skeleton', 8, {'target': 1, 'anim': 8, 'timer': 5, 'events': 0}, [], ['cos16', 'sin16', 'lead', 'v26'], {244: 5}),
    ('Skeleton', 8, {'target': 1, 'anim': 0, 'timer': 1}, [3], ['cos16', 'sin16', 'lead', 'v27'], {244: 0}),
    ('Skeleton', 16, {'ready': 1}, [0], ['ready', 'v27'], {}),
    ('Skeleton', 16, {}, [], ['ready', 'flee'], {}),
    ('Skeleton', 17, {'clock': 1000, 'timer': 0}, [3], ['v27'], {}),
    ('Skeleton', 17, {'clock': 100, 'timer': 5000}, [], [], {}),
    ('Skeleton', 18, {'anim': 0}, [3], ['v27'], {}),
    ('Skeleton', 18, {'anim': 16}, [], [], {}),
    ('Skeleton', 19, {}, [0], ['unstun', 'v27'], {}),
    ('Skeleton', 20, {}, [], ['dead'], {}),
    ('Skeleton', 23, {'anim': 0}, [0], ['fx', 'v27'], {}),
    ('Skeleton', 23, {'anim': 16}, [], ['fx'], {}),
    ('Skeleton', 7, {}, [], [], {}),
    ('Soul', 0, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': 5000}, [24], ['move_by', 'demon', 'v27'], {}),
    ('Soul', 0, {'frame': 0, 'demon': 0, 'clock': 100, 'timer': 5000}, [], ['move_by', 'demon', 'away'], {}),
    ('Soul', 0, {'frame': 1, 'clock': 100, 'timer': 5000, 'away': 1}, [1], ['move_by', 'away', 'v27'], {}),
    ('Soul', 0, {'frame': 1, 'clock': 1000, 'timer': 0}, [1], ['move_by', 'v27'], {}),
    ('Soul', 0, {'frame': 1, 'clock': 100, 'timer': 5000}, [], ['move_by', 'away'], {}),
    ('Soul', 0, {'owner': 1, 'frame': 0, 'demon': 1, 'clock': 100, 'timer': 5000}, [24], ['demon', 'v27'], {}),
    ('Soul', 1, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': 5000}, [24], ['move_by', 'demon', 'v27'], {}),
    ('Soul', 1, {'frame': 1, 'arrived': 1, 'clock': 100, 'timer': 5000}, [0], ['move_by', 'move_to', 'v27'], {}),
    ('Soul', 1, {'frame': 1, 'clock': 1000, 'timer': 0}, [0], ['move_by', 'move_to', 'v27'], {}),
    ('Soul', 1, {'frame': 1, 'clock': 100, 'timer': 5000}, [], ['move_by', 'move_to'], {}),
    ('Soul', 24, {'frame': 0, 'demon': 0, 'clock': 100, 'timer': 5000}, [0], ['move_by', 'demon', 'v27'], {}),
    ('Soul', 24, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': 5000}, [], ['move_by', 'demon'], {}),
    ('Soul', 24, {'frame': 1, 'demon': 0, 'clock': 100, 'timer': 5000}, [], ['move_by'], {}),
    ('Soul', 3, {}, [0], ['move_by', 'v27'], {}),
    ('Soul', 3, {'target': 1}, [], ['move_by'], {}),
    ('Soul', 5, {}, [0], ['move_by', 'unroot', 'v27'], {}),
    ('Soul', 5, {'rooted': 1}, [], ['move_by', 'unroot'], {}),
    ('Soul', 18, {'anim': 0}, [24], ['move_by', 'v27'], {}),
    ('Soul', 18, {'anim': 16}, [], ['move_by'], {}),
    ('Soul', 25, {'anim': 0}, [24], ['move_by', 'v27'], {}),
    ('Soul', 23, {'clock': 1000, 'timer': 0}, [1], ['move_by', 'v27'], {}),
    ('Soul', 23, {'clock': 100, 'timer': 5000}, [], ['move_by'], {}),
    ('Soul', 20, {'clock': 1000, 'timer': 0}, [], ['move_by', 'samples', 'delete'], {}),
    ('Soul', 20, {'clock': 100, 'timer': 5000}, [], ['move_by', 'samples'], {}),
    ('Soul', 20, {'anim': 128, 'clock': 100, 'timer': 5000}, [], ['move_by', 'samples', 'delete'], {}),
    ('Soul', 34, {'clock': 1000, 'timer': 0}, [], ['move_by', 'samples', 'stop'], {}),
    ('Soul', 34, {'clock': 100, 'timer': 5000}, [], ['move_by', 'samples'], {}),
    ('Soul', 34, {'anim': 128, 'clock': 100, 'timer': 5000}, [], ['move_by', 'samples', 'stop'], {}),
    ('Soul', 27, {'clock': 1000, 'timer': 0}, [], ['samples', 'mat_place', 'mat_rot', 'cos16', 'sin16', 'delete'], {}),
    ('Soul', 27, {'clock': 100, 'timer': 5000, 'z': 0}, [], ['samples', 'mat_place', 'mat_rot', 'cos16', 'sin16', 'terrain', 'delete'], {}),
    ('Soul', 27, {'clock': 100, 'timer': 5000, 'z': 1120403456}, [], ['samples', 'mat_place', 'mat_rot', 'cos16', 'sin16', 'terrain'], {}),
    ('Soul', 26, {'owner': 1}, [], [], {}),
    ('Soul', 6, {}, [], ['move_by'], {}),
]


class OwnMachinesTest(unittest.TestCase):
    def test_every_locked_tick(self):
        self.assertEqual(len(LOCKED), 253)
        for name, state, ctx, req, calls, words in LOCKED:
            with self.subTest(name=name, state=state, ctx=ctx):
                self.assertEqual(M.step(name, state, ctx), (req, calls, words))

    def test_context_is_not_mutated(self):
        ctx = {'seq': {'v25': [0, 1]}, 'queue': 1, 'clock': 100, 'timer': 5000}
        M.step('AntQueen', 0, ctx)
        self.assertEqual(ctx['seq']['v25'], [0, 1])

    def test_antqueen_second_sight_counts(self):
        # First slot 25 misses, second hits, queue below 4: state 3.
        req, calls, _ = M.step('AntQueen', 0, {
            'queue': 1, 'clock': 100, 'timer': 5000, 'seq': {'v25': [0, 1]}})
        self.assertEqual(req, [3])
        self.assertEqual(calls, ['aq_ground', 'v25', 'v25', 'v27'])

    def test_critter_fidget_blocks_wander(self):
        req, calls, _ = M.step('Critter', 0, {
            'fidget_a': 1, 'move': 1, 'clock': 1000, 'fid_time': 0, 'timer': 0})
        self.assertEqual(req, [])
        self.assertEqual(calls, ['move_by', 'anim_bio', 'rand'])

    def test_mermaid_ignores_arrival(self):
        req, calls, _ = M.step('Mermaid', 1, {'clock': 100, 'timer': 5000, 'arrived': 1})
        self.assertEqual(req, [])
        self.assertEqual(calls, ['move_by', 'move_dest'])

    def test_soul_alarm_phase(self):
        req, _, _ = M.step('Soul', 0, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': 5000})
        self.assertEqual(req, [0x18])
        req, calls, _ = M.step('Soul', 0x18, {'frame': 0, 'demon': 1, 'clock': 100, 'timer': 5000})
        self.assertEqual(req, [])
        self.assertEqual(calls, ['move_by', 'demon'])
        req, _, _ = M.step('Soul', 0x18, {'frame': 1, 'demon': 0, 'clock': 100, 'timer': 5000})
        self.assertEqual(req, [])

    def test_skeleton_empty_shot_then_countdown(self):
        req, calls, words = M.step('Skeleton', 8, {'anim': 0, 'timer': 1})
        self.assertEqual(req, [0, 3])
        self.assertEqual(calls, ['v27', 'v27'])
        self.assertEqual(words[0xf4], 0)

    def test_rise_flag_differs(self):
        _, sl, _ = M.step('Skelight', 0x17, {'anim': 0x80})
        _, sk, _ = M.step('Skeleton', 0x17, {'anim': 0})
        self.assertEqual(sl, ['v27', 'fx'])
        self.assertEqual(sk, ['fx', 'v27'])

    def test_natasla_decides_nothing(self):
        self.assertEqual(M.step('Natasla', 0, {'seen': 1, 'target': 1}), ([], [], {}))

    def test_npc_root_gate(self):
        self.assertFalse(M.root_clears_speed(0x3f000000))
        self.assertTrue(M.root_clears_speed(0x3f000001))
        self.assertTrue(M.root_clears_speed(0xbf000001))
        self.assertFalse(M.root_clears_speed(0))


if __name__ == '__main__':
    unittest.main()
