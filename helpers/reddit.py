
import asyncpraw
import html

async def get_reddit_post(url: str, bot):
    """
    Gets a Reddit post from a given URL.

    :param url: The URL of the Reddit post.
    :param bot: The bot instance.
    :return: A tuple containing the post content and image URL, or None.
    """
    if not bot.config.get("reddit_api_enabled", False):
        print("[DEBUG] Reddit API is disabled in config")
        return None

    try:
        client_secret = bot.config.get("reddit_client_secret")
        if not client_secret:
            client_secret = None  # Required for installed applications
        
        reddit = asyncpraw.Reddit(
            client_id=bot.config["reddit_client_id"],
            client_secret=client_secret,
            user_agent=bot.config["reddit_user_agent"],
        )
    except Exception as e:
        print(f"[DEBUG] Failed to initialize Reddit client: {e}")
        return None

    try:
        submission = await reddit.submission(url=url)
        await submission.load()
    except Exception as e:
        print(f"[DEBUG] Failed to get reddit post: {e}")
        return None

    image_url = None

    # 1) Direct image link on the post itself
    try:
        if isinstance(submission.url, str) and submission.url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
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
            print(f"[DEBUG] Error getting gallery image via media_metadata: {e}")

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
            print(f"[DEBUG] Error getting preview image: {e}")

    # 4) Known direct hosters even if missing extension (rare)
    if image_url is None and isinstance(submission.url, str) and ("i.redd.it" in submission.url or "i.imgur.com" in submission.url):
        image_url = submission.url

    # 5) Thumbnail as last resort (avoid default/self which are logos/placeholders)
    if image_url is None and submission.thumbnail and submission.thumbnail not in {"self", "default", "nsfw", "spoiler"}:
        image_url = submission.thumbnail

    # Create comprehensive content including title and text
    content_parts = []
    if submission.title:
        content_parts.append(f"Title: {submission.title}")
    if submission.selftext:
        content_parts.append(f"Content: {submission.selftext}")
    
    # Add metadata
    metadata = f"Posted in r/{submission.subreddit.display_name}"
    if hasattr(submission.author, 'name') and submission.author.name:
        metadata += f" by u/{submission.author.name}"
    metadata += f" with {submission.score} upvotes and {submission.num_comments} comments"
    content_parts.append(metadata)
    
    content = "\n\n".join(content_parts)

    print(f"[DEBUG] Reddit Post Details:")
    print(f"  Title: {submission.title}")
    print(f"  Subreddit: r/{submission.subreddit.display_name}")
    print(f"  Author: u/{submission.author.name}")
    print(f"  Score: {submission.score}")
    print(f"  Comments: {submission.num_comments}")
    print(f"  Submission URL: {submission.url}")
    print(f"  Thumbnail: {submission.thumbnail}")
    print(f"  Has preview: {hasattr(submission, 'preview') and submission.preview}")
    print(f"  Has gallery: {hasattr(submission, 'gallery_data') and submission.gallery_data}")
    print(f"  Final Image URL: {image_url}")
    print(f"  Content length: {len(content)}")

    return content, image_url
