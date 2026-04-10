from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional
import asyncio
import time
import logging

logger = logging.getLogger("omega.gei.adapters")

class GEISignal(dict):
    """A single signal from the external world."""
    def __init__(self, source: str, content: str, timestamp: Optional[float] = None, metadata: Optional[Dict[str, Any]] = None):
        super().__init__()
        self["source"] = source
        self["content"] = content
        self["timestamp"] = timestamp or time.time()
        self["metadata"] = metadata or {}

class BaseGEIAdapter(ABC):
    """Base class for all Global Event Inducer adapters."""

    @abstractmethod
    async def fetch_signals(self) -> List[GEISignal]:
        """Fetch raw signals from the source."""
        return []

    def name(self) -> str:
        return self.__class__.__name__


class WikipediaRecentAdapter(BaseGEIAdapter):
    """Adapter that queries Wikipedia for recent/notable topics."""

    # Fixed queries covering broad geopolitical, scientific, and social domains
    _QUERIES = [
        "recent geopolitical conflict 2026",
        "climate change extreme weather 2026",
        "emerging technology AI 2026",
        "global economic trends 2026",
        "public health outbreak 2026",
    ]

    async def fetch_signals(self) -> List[GEISignal]:
        loop = asyncio.get_event_loop()
        signals: List[GEISignal] = []
        try:
            import wikipedia_api  # type: ignore
        except ImportError:
            logger.warning("GEI WikipediaRecentAdapter: wikipedia_api module not available")
            return signals

        for query in self._QUERIES:
            try:
                results = await loop.run_in_executor(
                    None, lambda q=query: wikipedia_api.search_pages(q, limit=2)
                )
                for row in results:
                    snippet = str(row.get("snippet") or "").strip()
                    title = str(row.get("title") or "").strip()
                    if snippet:
                        signals.append(GEISignal(
                            source=f"Wikipedia:{title}",
                            content=f"{title} — {snippet}",
                            metadata={"url": row.get("url", ""), "query": query},
                        ))
            except Exception as e:
                logger.warning("GEI WikipediaRecentAdapter query '%s' failed: %s", query, e)

        return signals


class ArxivRecentAdapter(BaseGEIAdapter):
    """Adapter that queries arXiv for recent research signals."""

    _QUERIES = [
        "artificial intelligence safety alignment",
        "climate systems tipping points",
        "global economic systems complexity",
    ]

    async def fetch_signals(self) -> List[GEISignal]:
        loop = asyncio.get_event_loop()
        signals: List[GEISignal] = []
        try:
            import arxiv_api  # type: ignore
        except ImportError:
            logger.warning("GEI ArxivRecentAdapter: arxiv_api module not available")
            return signals

        for query in self._QUERIES:
            try:
                results = await loop.run_in_executor(
                    None, lambda q=query: arxiv_api.search_metadata(q, max_results=2)
                )
                for row in results:
                    title = str(row.get("title") or "").strip()
                    summary = str(row.get("summary") or "").strip()
                    if title and summary:
                        signals.append(GEISignal(
                            source=f"arXiv:{','.join((row.get('categories') or [])[:2])}",
                            content=f"{title}: {summary}",
                            metadata={"link": row.get("link", ""), "published": row.get("published", "")},
                        ))
            except Exception as e:
                logger.warning("GEI ArxivRecentAdapter query '%s' failed: %s", query, e)

        return signals
