"""What a currency code and an amount must be, before anything reaches the database.

These are the caller's mistakes, and each one is a refusal naming the field. The overdraft is
deliberately not here: whether a player can afford something is the database's question, asked
in the same statement that spends it.
"""

from __future__ import annotations

import pytest

from wavemaker.apps.economy.domain.wallet import (
    MAX_AMOUNT,
    InvalidRequest,
    currency_code,
    positive_amount,
)


@pytest.mark.parametrize("code", ["coins", "gems", "event_tokens_2026", "a" * 40])
def test_a_currency_is_the_projects_own_word(code: str) -> None:
    assert currency_code(code) == code


@pytest.mark.parametrize(
    "code",
    [None, "", "   ", "Coins", "gold coins", "coins!", "a" * 41, 7, ["coins"]],
)
def test_anything_else_is_refused_and_names_the_field(code: object) -> None:
    with pytest.raises(InvalidRequest) as refused:
        currency_code(code)
    assert refused.value.pointer == "/currency"


@pytest.mark.parametrize("amount", [1, 250, MAX_AMOUNT])
def test_an_amount_is_a_whole_positive_number(amount: int) -> None:
    assert positive_amount(amount) == amount


@pytest.mark.parametrize(
    "amount",
    [
        0,
        -5,
        None,
        "10",
        1.5,
        # bool is an int in Python. `{"amount": true}` is not one coin.
        True,
        MAX_AMOUNT + 1,
    ],
)
def test_an_amount_that_is_not_one_is_refused(amount: object) -> None:
    with pytest.raises(InvalidRequest) as refused:
        positive_amount(amount)
    assert refused.value.pointer == "/amount"
