"""Small, authored reference for hub savepoint use.

The disc census and the original EE function remain the source of evidence.
This model covers only direct use before card/UI services run.
"""


def savepoint_use(card_busy, menu_mutex_held):
    accepted = not (card_busy or menu_mutex_held)
    return {
        'request_save': accepted,
        'dispatch_action': accepted,
        'activated': int(accepted),
        'effect_pending': int(accepted),
        'player_record_changed': False,
    }
