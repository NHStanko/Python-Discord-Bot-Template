"""Shared HTTP client lifecycle for bot features."""

from __future__ import annotations

import asyncio

import aiohttp

_SESSION_ATTRIBUTE = "_shared_http_session"
_LOCK_ATTRIBUTE = "_shared_http_session_lock"


async def get_http_session(owner) -> aiohttp.ClientSession:
    """Return one lazily created HTTP session per bot-like owner."""
    session = getattr(owner, _SESSION_ATTRIBUTE, None)
    if session is not None and not session.closed:
        return session

    lock = getattr(owner, _LOCK_ATTRIBUTE, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(owner, _LOCK_ATTRIBUTE, lock)
    async with lock:
        session = getattr(owner, _SESSION_ATTRIBUTE, None)
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            setattr(owner, _SESSION_ATTRIBUTE, session)
        return session


async def close_http_session(owner) -> None:
    """Close and clear the shared HTTP session, if one exists."""
    lock = getattr(owner, _LOCK_ATTRIBUTE, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(owner, _LOCK_ATTRIBUTE, lock)
    async with lock:
        session = getattr(owner, _SESSION_ATTRIBUTE, None)
        setattr(owner, _SESSION_ATTRIBUTE, None)
        if session is not None and not session.closed:
            await session.close()
