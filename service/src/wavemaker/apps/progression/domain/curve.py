"""How far a player has come: XP, the project's curve, and the stage one implies on the other.

A stage is never stored. It is derived from a player's XP and the curve, so editing the curve
moves every player to the stage the new curve gives them, at once, with nothing to migrate.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass

from wavemaker.platform.kernel.storable import unstorable

MAX_XP = 2**63 - 1  # a bigint
MAX_STAGE = 2**31 - 1  # an integer
MAX_LABEL_LENGTH = 120


@dataclass(frozen=True, slots=True)
class Stage:
    stage: int
    xp_required: int  # cumulative: the total XP at which this stage begins
    label: str | None


@dataclass(frozen=True, slots=True)
class Progress:
    """Where a player is. Both stages are None when the project has no curve; `stage` is None
    while a player's XP is below the first stage; `next_stage` is None at the top."""

    xp: int
    stage: Stage | None
    next_stage: Stage | None


@dataclass(frozen=True, slots=True)
class Grant:
    currency: str
    amount: int


@dataclass(frozen=True, slots=True)
class Reward:
    grants: list[Grant]
    xp: int


class ProgressionError(Exception):
    """A request about progress that was understood and not acted on."""


class Rejected(ProgressionError):
    """Every problem with a request, each starting with the pointer to the field at fault, so
    an author sees them all at once rather than one per attempt."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class NoSuchPlayer(ProgressionError):
    """The player is not in this project, or no longer anywhere."""


class TooMuchXp(ProgressionError):
    """An award that would take a player's XP past what can be stored."""


def reached(curve: Sequence[Stage], xp: int) -> Stage | None:
    """The highest stage whose threshold `xp` has met. `curve` is in ascending order."""
    found = None
    for stage in curve:
        if stage.xp_required > xp:
            break
        found = stage
    return found


def following(curve: Sequence[Stage], xp: int) -> Stage | None:
    """The first stage `xp` has not yet met."""
    return next((stage for stage in curve if stage.xp_required > xp), None)


def progress(curve: Sequence[Stage], xp: int) -> Progress:
    return Progress(xp=xp, stage=reached(curve, xp), next_stage=following(curve, xp))


def _whole(value: object, low: int, high: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and low <= value <= high


def curve_of(stages: object) -> list[Stage]:
    """A whole curve from a request, in ascending order, or `Rejected` with every problem.

    Wholesale, because stages only mean something relative to each other: edited one at a time,
    stage 3 can end up beginning before stage 2. Problems are reported at the index the request
    sent. The Java sorted first and reported the index in its sorted copy, so an author was
    pointed at the wrong row whenever they had not sent the stages in order.
    """
    if not isinstance(stages, list):
        raise Rejected(["/stages: send the stages, even an empty list"])

    problems: list[str] = []
    parsed: list[tuple[int, Stage]] = []
    for index, item in enumerate(stages):
        where = f"/stages/{index}"
        if not isinstance(item, dict):
            problems.append(f"{where}: a stage is an object")
            continue
        stage, xp_required, label = item.get("stage"), item.get("xpRequired"), item.get("label")
        valid = True
        if not _whole(stage, 0, MAX_STAGE):
            problems.append(f"{where}/stage: a stage is a whole number from 0 to {MAX_STAGE}")
            valid = False
        if not _whole(xp_required, 0, MAX_XP):
            problems.append(f"{where}/xpRequired: a threshold is a whole number from 0 to {MAX_XP}")
            valid = False
        if label is not None and not isinstance(label, str):
            problems.append(f"{where}/label: a label is text")
            valid = False
        elif isinstance(label, str) and (unusable := unstorable(label)):
            problems.append(f"{where}/label: {unusable}")
            valid = False
        elif isinstance(label, str) and len(label.strip()) > MAX_LABEL_LENGTH:
            problems.append(f"{where}/label: a label is at most {MAX_LABEL_LENGTH} characters")
            valid = False
        if valid:
            assert isinstance(stage, int) and isinstance(xp_required, int)
            text = label.strip() if isinstance(label, str) else ""
            parsed.append((index, Stage(stage, xp_required, text or None)))

    ordered = sorted(parsed, key=lambda pair: pair[1].stage)
    for (_, previous), (index, current) in itertools.pairwise(ordered):
        if current.stage == previous.stage:
            problems.append(f"/stages/{index}/stage: stage {current.stage} is listed twice")
        elif current.xp_required <= previous.xp_required:
            # A later stage beginning at or before an earlier one makes "which stage is this" a
            # guess, and the unique index would refuse it anyway — as a constraint name, which
            # is not something an author can act on.
            problems.append(
                f"/stages/{index}/xpRequired: stage {current.stage} must begin after stage "
                f"{previous.stage}, which begins at {previous.xp_required}"
            )
    if problems:
        raise Rejected(problems)
    return [stage for _, stage in ordered]


def reward_of(body: dict[str, object]) -> Reward:
    """The grants and XP of a reward, or `Rejected` with every problem.

    Only the shape of a currency is checked here. Which currencies exist, and what a code may
    look like, is the business of the app that holds currency, which refuses through the port.
    """
    problems: list[str] = []
    grants: list[Grant] = []
    raw_grants = body.get("grants")
    if raw_grants is None:
        raw_grants = []
    if not isinstance(raw_grants, list):
        problems.append("/grants: grants are a list")
        raw_grants = []
    for index, item in enumerate(raw_grants):
        where = f"/grants/{index}"
        if not isinstance(item, dict):
            problems.append(f"{where}: a grant is an object")
            continue
        currency, amount = item.get("currency"), item.get("amount")
        valid = True
        if not isinstance(currency, str) or not currency:
            problems.append(f"{where}/currency: a grant names its currency")
            valid = False
        if not _whole(amount, 1, MAX_XP):
            problems.append(f"{where}/amount: an amount is a whole number from 1 to {MAX_XP}")
            valid = False
        if valid:
            assert isinstance(currency, str) and isinstance(amount, int)
            grants.append(Grant(currency, amount))

    xp = body.get("xp")
    if xp is None:
        xp = 0
    if not _whole(xp, 0, MAX_XP):
        # Never negative: a reward does not take XP away, and a route that could would be a
        # way to move a player down a stage that nobody designed.
        problems.append(f"/xp: XP is a whole number from 0 to {MAX_XP}")
    if problems:
        raise Rejected(problems)
    assert isinstance(xp, int)
    return Reward(grants=grants, xp=xp)
