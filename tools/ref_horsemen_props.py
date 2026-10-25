"""Addressed reference for the four Nightmare property lists in SLUS_209.73 v2.00.

Each 12-byte list is two pointers followed by a null pointer.  The values below are
decoded property fields, not an executable image or a copy of its byte ranges.
"""
from collections import namedtuple


MountProperties = namedtuple('MountProperties',
                             'variant list_addr miniboss_entry_addr name_entry_addr '
                             'terminator_addr miniboss_text_addr name_text_addr miniboss name')


MOUNT_PROPERTIES = tuple(
    MountProperties(variant, 0x500848 + 12 * variant,
                    0x500848 + 12 * variant, 0x50084C + 12 * variant,
                    0x500850 + 12 * variant, 0x547320, name_addr, 1, name)
    for variant, name_addr, name in (
        (0, 0x547330, b'horsedisease'),
        (1, 0x547348, b'horsewar'),
        (2, 0x547358, b'horsepestilence'),
        (3, 0x547370, b'horsedeath'),
    )
)
