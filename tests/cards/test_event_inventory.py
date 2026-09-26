from pog_engine.data import load_data
from pog_engine.rules.cards import EVENT_HANDLERS


def test_every_historical_base_card_has_a_registered_handler():
    assert set(EVENT_HANDLERS) == set(load_data().cards)
    assert len(EVENT_HANDLERS) == 110
    assert all(callable(getattr(handler, name, None)) for handler in EVENT_HANDLERS.values()
               for name in ("can_play", "legal_choices", "apply"))
