from decimal import Decimal

import pytest


@pytest.mark.parametrize('cents,category', [(0,'LOW'), (9999,'LOW'), (10000,'STANDARD'), (999999,'STANDARD'), (1000000,'PREMIUM')])
def test_category_boundaries(cents, category):
    from app.notifications import category_for
    assert category_for(cents) == category


@pytest.mark.parametrize('category,opted_in,kinds', [
    ('LOW',False,['LOW_BALANCE_ALERT']),
    ('LOW',True,['LOW_BALANCE_ALERT','LOW_BALANCE_MARKETING']),
    ('STANDARD',True,[]), ('PREMIUM',False,[]),
    ('PREMIUM',True,['PREMIUM_MARKETING']),
])
def test_marketing_respects_opt_in(category, opted_in, kinds):
    from app.notifications import message_templates
    messages = message_templates(category, opted_in)
    assert [m['kind'] for m in messages] == kinds
    for message in messages:
        if message['kind'] == 'LOW_BALANCE_MARKETING':
            assert 'Eligibility and approval depend on assessment.' in message['message']


def test_exact_money_round_trip():
    from app.models import to_cents, from_cents
    assert to_cents(Decimal('0.10')) == 10
    assert str(from_cents(30)) == '0.30'
