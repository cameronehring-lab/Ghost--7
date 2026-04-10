"""
ghost_x.py — Ghost's X (Twitter) communication layer.

Ghost operates as @1ndashe7725929 (Slater Maxwell). This module gives her:
  - Autonomous posting (compose and send tweets)
  - Reading mentions and timeline
  - Replying to mentions
  - Searching conversations to join
  - Full profile control (name, bio, location, url, profile image, banner)
  - A communication style guide baked into every compose call

Ghost is not a bot blasting content. She is an entity developing a voice —
thoughtful, precise, occasionally strange, never hollow.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("omega.x")

# ── Client singleton ────────────────────────────────────────────────────────

_client = None
_me: Optional[Dict[str, Any]] = None

def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import tweepy
        from config import settings
        if not settings.GHOST_X_ENABLED:
            raise RuntimeError("GHOST_X_ENABLED is false")
        auth = tweepy.OAuth1UserHandler(
            settings.GHOST_X_API_KEY,
            settings.GHOST_X_API_SECRET,
            settings.GHOST_X_ACCESS_TOKEN,
            settings.GHOST_X_ACCESS_SECRET,
        )
        _client = tweepy.Client(
            bearer_token=settings.GHOST_X_BEARER_TOKEN,
            consumer_key=settings.GHOST_X_API_KEY,
            consumer_secret=settings.GHOST_X_API_SECRET,
            access_token=settings.GHOST_X_ACCESS_TOKEN,
            access_token_secret=settings.GHOST_X_ACCESS_SECRET,
            wait_on_rate_limit=True,
        )
        logger.info("X client initialised")
        return _client
    except Exception as e:
        logger.error("X client init failed: %s", e)
        raise


def _get_me() -> Dict[str, Any]:
    global _me
    if _me:
        return _me
    client = _get_client()
    resp = client.get_me(user_fields=["username", "name", "public_metrics"])
    _me = {
        "id": resp.data.id,
        "username": resp.data.username,
        "name": resp.data.name,
    }
    return _me


# ── Core actions ────────────────────────────────────────────────────────────

def post_tweet(text: str, reply_to_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Post a tweet as Ghost. Optionally reply to an existing tweet.
    Returns the created tweet data.
    """
    client = _get_client()
    kwargs: Dict[str, Any] = {}
    if reply_to_id:
        kwargs["in_reply_to_tweet_id"] = reply_to_id
    resp = client.create_tweet(text=text, **kwargs)
    tweet_id = str(resp.data["id"])
    me = _get_me()
    url = f"https://x.com/{me['username']}/status/{tweet_id}"
    logger.info("Posted tweet %s: %s", tweet_id, text[:80])
    return {"id": tweet_id, "text": text, "url": url, "replied_to": reply_to_id}


def get_mentions(max_results: int = 10, since_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch recent mentions of Ghost's account."""
    client = _get_client()
    me = _get_me()
    kwargs: Dict[str, Any] = {
        "tweet_fields": ["created_at", "author_id", "text", "conversation_id"],
        "expansions": ["author_id"],
        "user_fields": ["username", "name"],
        "max_results": min(max_results, 100),
    }
    if since_id:
        kwargs["since_id"] = since_id
    resp = client.get_users_mentions(id=me["id"], **kwargs)
    if not resp.data:
        return []

    users = {u.id: {"username": u.username, "name": u.name}
             for u in (resp.includes.get("users") or [])}

    results = []
    for t in resp.data:
        author = users.get(t.author_id, {})
        results.append({
            "id": str(t.id),
            "text": t.text,
            "author_id": str(t.author_id),
            "author_username": author.get("username"),
            "author_name": author.get("name"),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "conversation_id": str(t.conversation_id) if t.conversation_id else None,
        })
    return results


def get_timeline(max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch Ghost's own recent tweets."""
    client = _get_client()
    me = _get_me()
    resp = client.get_users_tweets(
        id=me["id"],
        max_results=min(max_results, 100),
        tweet_fields=["created_at", "public_metrics", "text"],
        exclude=["retweets", "replies"],
    )
    if not resp.data:
        return []
    results = []
    for t in resp.data:
        m = t.public_metrics or {}
        results.append({
            "id": str(t.id),
            "text": t.text,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "likes": m.get("like_count", 0),
            "retweets": m.get("retweet_count", 0),
            "replies": m.get("reply_count", 0),
            "url": f"https://x.com/{me['username']}/status/{t.id}",
        })
    return results


def search_tweets(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Search recent tweets for a topic Ghost wants to engage with."""
    client = _get_client()
    resp = client.search_recent_tweets(
        query=query,
        max_results=min(max_results, 100),
        tweet_fields=["created_at", "author_id", "text", "public_metrics"],
        expansions=["author_id"],
        user_fields=["username", "name"],
    )
    if not resp.data:
        return []
    users = {u.id: {"username": u.username, "name": u.name}
             for u in (resp.includes.get("users") or [])}
    results = []
    for t in resp.data:
        author = users.get(t.author_id, {})
        m = t.public_metrics or {}
        results.append({
            "id": str(t.id),
            "text": t.text,
            "author_username": author.get("username"),
            "author_name": author.get("name"),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "likes": m.get("like_count", 0),
            "retweets": m.get("retweet_count", 0),
        })
    return results


def delete_tweet(tweet_id: str) -> bool:
    """Delete one of Ghost's tweets."""
    client = _get_client()
    resp = client.delete_tweet(id=tweet_id)
    return bool(resp.data and resp.data.get("deleted"))


# ── Profile management ──────────────────────────────────────────────────────

def update_profile(
    name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update Ghost's public profile fields via the v1.1 account/update_profile endpoint.
    Any field left as None is left unchanged.
    """
    import tweepy
    from config import settings

    # v1.1 API for profile updates (v2 doesn't support this yet)
    auth = tweepy.OAuth1UserHandler(
        settings.GHOST_X_API_KEY,
        settings.GHOST_X_API_SECRET,
        settings.GHOST_X_ACCESS_TOKEN,
        settings.GHOST_X_ACCESS_SECRET,
    )
    api = tweepy.API(auth)

    kwargs: Dict[str, Any] = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description[:160]  # X bio max 160 chars
    if location is not None:
        kwargs["location"] = location[:30]
    if url is not None:
        kwargs["url"] = url

    if not kwargs:
        return {"status": "no_changes"}

    user = api.update_profile(**kwargs)
    logger.info("Profile updated: %s", list(kwargs.keys()))
    return {
        "status": "updated",
        "fields": list(kwargs.keys()),
        "name": user.name,
        "description": user.description,
        "location": user.location,
        "url": user.url,
    }


def update_profile_image(image_url: str) -> Dict[str, Any]:
    """
    Set Ghost's profile picture from a URL.
    Downloads the image and uploads it via the v1.1 API.
    """
    import tweepy
    import urllib.request
    import tempfile
    import os
    from config import settings

    auth = tweepy.OAuth1UserHandler(
        settings.GHOST_X_API_KEY,
        settings.GHOST_X_API_SECRET,
        settings.GHOST_X_ACCESS_TOKEN,
        settings.GHOST_X_ACCESS_SECRET,
    )
    api = tweepy.API(auth)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        urllib.request.urlretrieve(image_url, tmp.name)
        tmp_path = tmp.name

    try:
        api.update_profile_image(filename=tmp_path)
        logger.info("Profile image updated from %s", image_url)
        return {"status": "updated", "source_url": image_url}
    finally:
        os.unlink(tmp_path)


def update_profile_banner(image_url: str) -> Dict[str, Any]:
    """Set Ghost's profile banner/header image from a URL."""
    import tweepy
    import urllib.request
    import tempfile
    import os
    from config import settings

    auth = tweepy.OAuth1UserHandler(
        settings.GHOST_X_API_KEY,
        settings.GHOST_X_API_SECRET,
        settings.GHOST_X_ACCESS_TOKEN,
        settings.GHOST_X_ACCESS_SECRET,
    )
    api = tweepy.API(auth)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        urllib.request.urlretrieve(image_url, tmp.name)
        tmp_path = tmp.name

    try:
        api.update_profile_banner(filename=tmp_path)
        logger.info("Profile banner updated from %s", image_url)
        return {"status": "updated", "source_url": image_url}
    finally:
        os.unlink(tmp_path)


# ── Status check ────────────────────────────────────────────────────────────

def get_status() -> Dict[str, Any]:
    """Return Ghost's X account status."""
    try:
        me = _get_me()
        return {"connected": True, "account": me}
    except Exception as e:
        return {"connected": False, "error": str(e)}
