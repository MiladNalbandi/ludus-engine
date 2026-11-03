"""The inventory routes: an editor's catalogue, an editor's grants, and a player's own view.

**A player may look and may not be given anything, and that is the trust model.** A forged
grant would make an inventory whatever a modified binary says it is, so giving and taking is an
admin route, behind a credential that does not ship inside the game. A game with no server of
its own therefore cannot award items through this service — a real limit, stated plainly
rather than a hole left open to avoid admitting it.

The player route is `/me` and takes no player id, so there is no handler that could forget to
check that the id is the caller's. The admin routes take one, because an editor acts on
somebody else by definition.

Paths, operation ids and field names are the frozen v1 contract's. The schema has its own path,
`/admin/item-schema`, rather than `/admin/items/schema`, which would make an item called
`schema` unreachable — the reason the Java gave it one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from wavemaker.platform.identity import players
from wavemaker.platform.identity.http import CurrentPlayer, Database, requires
from wavemaker.platform.identity.tokens import Role

from ..application import catalogue as use_cases
from ..application.ports import Catalogue, Inventories, SchemaValidator
from ..domain import attribute_schema, grant
from ..domain.errors import NoSuchPlayer, Rejected
from ..domain.item import MAX_ID_LENGTH, InventoryEntry, Item, is_slug
from .postgres import PostgresCatalogue, PostgresInventories
from .validation import JsonSchemaValidator

admin_router = APIRouter(prefix="/api/v1/admin", tags=["inventory"])
player_router = APIRouter(prefix="/api/v1/player/me", tags=["inventory"])

# Items are content: an editor decides what exists, as with waves, and decides what players
# receive, as with currency. A viewer may not look either, as in the Java, whose authorisation
# matrix put /admin/items, /admin/item-schema and /admin/players/** behind EDITOR.
EDITOR = Depends(requires(Role.EDITOR, Role.ADMIN))

VALIDATOR = JsonSchemaValidator()


def get_catalogue(db: Database) -> Catalogue:
    """The request's own session. With no database the platform answers 503 before this runs:
    an empty catalogue would tell an editor the project defines nothing, which is untrue."""
    session, project, _ = db
    return PostgresCatalogue(session, project)


def get_inventories(db: Database) -> Inventories:
    session, project, _ = db
    return PostgresInventories(session, project)


def get_validator() -> SchemaValidator:
    return VALIDATOR


Items = Annotated[Catalogue, Depends(get_catalogue)]
Holdings = Annotated[Inventories, Depends(get_inventories)]
Validator = Annotated[SchemaValidator, Depends(get_validator)]


def _moment(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _item(item: Item) -> dict[str, Any]:
    """`ItemView`. The attributes go out as the text they came in as, inside a string, exactly
    as the contract and the Java have it."""
    return {
        "id": item.id,
        "name": item.name,
        "itemType": item.item_type,
        "spriteRef": item.sprite_ref,
        "attributes": item.attributes,
        "createdAt": _moment(item.created_at),
        "updatedAt": _moment(item.updated_at),
    }


def _inventory(entries: Any) -> dict[str, Any]:
    """`PlayerInventory`."""
    return {"items": [_entry(entry) for entry in entries]}


def _entry(entry: InventoryEntry) -> dict[str, Any]:
    return {
        "itemId": entry.item_id,
        "quantity": entry.quantity,
        "updatedAt": _moment(entry.updated_at),
    }


def _refused(problem: Rejected) -> HTTPException:
    return HTTPException(status_code=422, detail=str(problem))


def _no_item() -> HTTPException:
    return HTTPException(status_code=404, detail="No such item.")


def _player_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as unknown:
        raise HTTPException(status_code=404, detail="No such player.") from unknown


# --- the catalogue ----------------------------------------------------------------------------


@admin_router.get("/items", operation_id="listItems", dependencies=[EDITOR])
def list_items(catalogue: Items) -> list[dict[str, Any]]:
    return [_item(item) for item in catalogue.items()]


@admin_router.get("/items/{item_id}", operation_id="getItem", dependencies=[EDITOR])
def get_item(item_id: str, catalogue: Items) -> dict[str, Any]:
    # Not an id and not there are one answer: either way there is nothing at this address.
    found = catalogue.find(item_id) if is_slug(item_id, MAX_ID_LENGTH) else None
    if found is None:
        raise _no_item()
    return _item(found)


@admin_router.put("/items/{item_id}", operation_id="saveItem", dependencies=[EDITOR])
def save_item(
    item_id: str, body: dict[str, Any], catalogue: Items, validator: Validator
) -> dict[str, Any]:
    """Create or replace. 200 either way, as the contract and the Java have it: a PUT names
    the item, so whether it existed before is not something the caller needs to branch on."""
    try:
        return _item(use_cases.save_item(catalogue, validator, item_id, body))
    except Rejected as problem:
        raise _refused(problem) from problem


@admin_router.delete(
    "/items/{item_id}", operation_id="deleteItem", dependencies=[EDITOR], status_code=204
)
def delete_item(item_id: str, catalogue: Items) -> Response:
    """204, as the Java answered. The contract lists 200 because the generator writes the
    default when an annotation says nothing; what a client has received is 204.

    Every player holding the item loses it, by a foreign key rather than a loop that might
    miss someone."""
    if not is_slug(item_id, MAX_ID_LENGTH) or not catalogue.delete(item_id):
        raise _no_item()
    return Response(status_code=204)


# --- the schema the catalogue answers to --------------------------------------------------------


@admin_router.get("/item-schema", operation_id="getItemSchema", dependencies=[EDITOR])
def get_item_schema(catalogue: Items) -> Response:
    """The schema exactly as it was set, or `{}` — which validates nothing — when there is
    none."""
    stored = catalogue.schema_text()
    return Response(
        content=attribute_schema.EMPTY if stored is None else stored,
        media_type="application/json",
    )


async def schema_body(request: Request) -> bytes:
    """The body, read only as far as the limit and one byte past it.

    So a body of a gigabyte costs this service sixty-four kilobytes before it is refused, and
    the rest is never read. A dependency rather than the route itself, so the route can stay
    synchronous and its database work runs off the event loop like every other route's.
    """
    limit = attribute_schema.MAX_SCHEMA_BYTES + 1
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) >= limit:
            break
    return bytes(received[:limit])


SchemaBody = Annotated[bytes, Depends(schema_body)]


@admin_router.put(
    "/item-schema",
    operation_id="replaceItemSchema",
    dependencies=[EDITOR],
    # Read by hand, so described by hand: the body is the schema itself, as the contract has it.
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"type": "string"}}},
        }
    },
)
def replace_item_schema(raw: SchemaBody, catalogue: Items, validator: Validator) -> Response:
    """The body is the schema, stored as the text it is and answered with the same text."""
    try:
        stored = use_cases.replace_schema(catalogue, validator, raw)
    except Rejected as problem:
        raise _refused(problem) from problem
    return Response(content=stored, media_type="application/json")


# --- an editor, on somebody's inventory ---------------------------------------------------------


@admin_router.get(
    "/players/{player_id}/inventory",
    operation_id="getPlayerInventoryAsAdmin",
    dependencies=[EDITOR],
)
def get_player_inventory_as_admin(
    player_id: str, inventories: Holdings, db: Database
) -> dict[str, Any]:
    player = _player_id(player_id)
    session, project, _ = db
    # An inventory does not know who exists, and an empty one is the normal state of a new
    # player, so whether there is a player at all is the platform's question.
    if players.find(session, project, player) is None:
        raise HTTPException(status_code=404, detail="No such player.")
    return _inventory(inventories.of(player))


@admin_router.post(
    "/players/{player_id}/inventory/grant",
    operation_id="grantPlayerItems",
    dependencies=[EDITOR],
)
def grant_player_items(
    player_id: str, body: dict[str, Any], inventories: Holdings
) -> dict[str, Any]:
    """All or nothing, and answered with everything the player then holds.

    The Java answered with only the lines it had changed. `PlayerInventory` is described by the
    contract as everything a player holds, the player route answers with that, and a client
    reading one shape from two routes should find the same thing in it.
    """
    player = _player_id(player_id)
    try:
        lines = grant.lines_of(body)
        return _inventory(inventories.grant(player, lines))
    except NoSuchPlayer as missing:
        raise HTTPException(status_code=404, detail="No such player.") from missing
    except Rejected as problem:
        raise _refused(problem) from problem


# --- a player, on their own inventory -----------------------------------------------------------


@player_router.get("/inventory", operation_id="getPlayerInventory")
def get_player_inventory(caller: CurrentPlayer, inventories: Holdings) -> dict[str, Any]:
    """Read-only. Receiving items needs a credential that does not ship in the game."""
    return _inventory(inventories.of(caller.player))
