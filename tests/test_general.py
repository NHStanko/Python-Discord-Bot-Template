import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cogs.general import General


@pytest.mark.parametrize("count, name_length", [(5, 5), (60, 5), (50, 100), (250, 100)])
def test_serverinfo_role_field_fits_discord_limit(count, name_length):
    role_names = [f"{i:03d}" + "x" * (name_length - 3) for i in range(count)]
    guild = SimpleNamespace(
        roles=[SimpleNamespace(name=name) for name in role_names],
        icon=None,
        id=123,
        member_count=100,
        channels=[],
        created_at="2026-01-01",
    )
    context = SimpleNamespace(guild=guild, send=AsyncMock())

    asyncio.run(General.serverinfo.callback(General(None), context))

    embed = context.send.call_args.kwargs["embed"]
    field = next(field for field in embed.fields if field.name.startswith("Roles"))
    assert field.name == f"Roles ({count})"
    assert 0 < len(field.value) <= 1024
    displayed = field.value.split("\n")[0].split(", ")
    assert displayed == role_names[: len(displayed)]
    assert len(displayed) <= 50
    if len(displayed) < count:
        assert field.value.endswith(f"Showing {len(displayed)}/{count} roles")
    else:
        assert field.value == ", ".join(role_names)
