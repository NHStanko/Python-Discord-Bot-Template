import asyncio
import html
import logging

import asyncpraw

logger = logging.getLogger("discord_bot")

_REDDIT_CLIENT_ATTRIBUTE = "_reddit_client"
_REDDIT_CONFIG_ATTRIBUTE = "_reddit_client_config"
_REDDIT_LOCK_ATTRIBUTE = "_reddit_client_lock"


async def _close_client(client) -> None:
    if client is None:
        return
    try:
        await client.close()
    except Exception as exc:
        logger.warning("Failed to close Reddit client: %s", exc)


async def close_reddit_client(bot) -> None:
    """Close the cached AsyncPRAW client attached to a bot, if any."""
    lock = getattr(bot, _REDDIT_LOCK_ATTRIBUTE, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(bot, _REDDIT_LOCK_ATTRIBUTE, lock)
    async with lock:
        client = getattr(bot, _REDDIT_CLIENT_ATTRIBUTE, None)
        setattr(bot, _REDDIT_CLIENT_ATTRIBUTE, None)
        setattr(bot, _REDDIT_CONFIG_ATTRIBUTE, None)
        await _close_client(client)


async def _get_reddit_client(bot):
    client_id = bot.config.get("reddit_client_id")
    client_secret = bot.config.get("reddit_client_secret") or None
    user_agent = bot.config.get("reddit_user_agent")
    config_key = (client_id, client_secret, user_agent)

    lock = getattr(bot, _REDDIT_LOCK_ATTRIBUTE, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(bot, _REDDIT_LOCK_ATTRIBUTE, lock)
    async with lock:
        client = getattr(bot, _REDDIT_CLIENT_ATTRIBUTE, None)
        if (
            client is not None
            and getattr(bot, _REDDIT_CONFIG_ATTRIBUTE, None) == config_key
        ):
            return client

        if client is not None:
            setattr(bot, _REDDIT_CLIENT_ATTRIBUTE, None)
            setattr(bot, _REDDIT_CONFIG_ATTRIBUTE, None)
            await _close_client(client)

        try:
            client = asyncpraw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
        except Exception as exc:
            logger.warning("Failed to initialize Reddit client: %s", exc)
            return None

        setattr(bot, _REDDIT_CLIENT_ATTRIBUTE, client)
        setattr(bot, _REDDIT_CONFIG_ATTRIBUTE, config_key)
        return client


async def get_reddit_post(url: str, bot):
    """
    Gets a Reddit post from a given URL.

    :param url: The URL of the Reddit post.
    :param bot: The bot instance.
    :return: A tuple containing the post content and image URL, or None.
    """
    if not bot.config.get("reddit_api_enabled", False):
        logger.debug("Reddit API is disabled in config")
        return None

    reddit = await _get_reddit_client(bot)
    if reddit is None:
        return None

    try:
        submission = await reddit.submission(url=url)
        await submission.load()
    except Exception as e:
        logger.warning("Failed to load Reddit post: %s", e)
        return None

    image_url = None

    # 1) Direct image link on the post itself
    try:
        if isinstance(submission.url, str) and submission.url.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".webp")
        ):
            image_url = submission.url
    except Exception:
        pass

    # 2) Reddit gallery using media_metadata (most reliable for galleries)
    if image_url is None and getattr(submission, "gallery_data", None):
        try:
            gallery_items = (submission.gallery_data or {}).get("items", [])
            for item in gallery_items:
                media_id = item.get("media_id")
                meta = (submission.media_metadata or {}).get(media_id, {})
                if not meta:
                    continue
                if meta.get("e") == "Image":
                    source = meta.get("s", {})
                    # Prefer the full-size source URL
                    candidate = source.get("u")
                    # Fallback: highest resolution available
                    if not candidate:
                        resolutions = source.get("resolutions", [])
                        if resolutions:
                            candidate = resolutions[-1].get("url")
                    if candidate:
                        image_url = html.unescape(candidate)
                        break
        except Exception as e:
            logger.debug("Could not read Reddit gallery metadata: %s", e)

    # 3) Preview images for single-image posts
    if image_url is None and getattr(submission, "preview", None):
        try:
            images = submission.preview.get("images", [])
            if images:
                # Prefer the full-size source URL
                candidate = images[0].get("source", {}).get("url")
                # Fallback: try the highest resolution available
                if not candidate:
                    resolutions = images[0].get("resolutions", [])
                    if resolutions:
                        candidate = resolutions[-1].get("url")
                if candidate:
                    image_url = html.unescape(candidate)
        except Exception as e:
            logger.debug("Could not read Reddit preview image: %s", e)

    # 4) Known direct hosters even if missing extension (rare)
    if (
        image_url is None
        and isinstance(submission.url, str)
        and ("i.redd.it" in submission.url or "i.imgur.com" in submission.url)
    ):
        image_url = submission.url

    # 5) Thumbnail as last resort (avoid default/self which are logos/placeholders)
    if (
        image_url is None
        and submission.thumbnail
        and submission.thumbnail not in {"self", "default", "nsfw", "spoiler"}
    ):
        image_url = submission.thumbnail

    # Create comprehensive content including title and text
    content_parts = []
    if submission.title:
        content_parts.append(f"Title: {submission.title}")
    if submission.selftext:
        content_parts.append(f"Content: {submission.selftext}")

    # Add metadata
    metadata = f"Posted in r/{submission.subreddit.display_name}"
    if hasattr(submission.author, "name") and submission.author.name:
        metadata += f" by u/{submission.author.name}"
    metadata += (
        f" with {submission.score} upvotes and {submission.num_comments} comments"
    )
    content_parts.append(metadata)

    content = "\n\n".join(content_parts)

    logger.debug(
        "Loaded Reddit post metadata (content=%s characters, image=%s)",
        len(content),
        image_url is not None,
    )

    return content, image_url
