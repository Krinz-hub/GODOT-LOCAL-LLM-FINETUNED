"""Godot official documentation source connector."""

from typing import List, Optional
import requests
from logic_pipeline.sources.base import BaseSource, SourceItem
from logic_pipeline.rate_limit import RateLimiter, backoff_retry
from logic_pipeline.logging_config import get_logger

logger = get_logger("sources.docs")


class GodotDocsSource(BaseSource):
    """Retrieves Godot tutorials and reference material from approved doc sources."""

    def __init__(
        self,
        base_urls: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        version: str = "4.x",
        max_pages: int = 50,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        super().__init__(name="docs")
        self.base_urls = base_urls or ["https://docs.godotengine.org/en/stable/"]
        self.sections = sections or [
            "tutorials/scripting/gdscript/gdscript_basics.html",
            "tutorials/scripting/nodes_and_scene_instances.html",
            "tutorials/2d/2d_movement.html",
            "tutorials/physics/physics_introduction.html",
            "classes/class_node.html",
            "classes/class_characterbody2d.html",
        ]
        self.version = version
        self.max_pages = max_pages
        self.rate_limiter = rate_limiter or RateLimiter(requests_per_minute=20)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "GodotLogicAgent-DocsCrawler/1.0"})

    def discover(self, limit: Optional[int] = None) -> List[SourceItem]:
        """Lists candidate documentation pages."""
        items: List[SourceItem] = []
        base = self.base_urls[0] if self.base_urls else "https://docs.godotengine.org/en/stable/"
        max_count = limit or self.max_pages

        for section in self.sections:
            url = f"{base.rstrip('/')}/{section.lstrip('/')}"
            doc_id = f"docs:godot4:{section.replace('/', '_').replace('.html', '')}"

            item = SourceItem(
                item_id=doc_id,
                source_type="docs",
                source_url=url,
                repository="godotengine/godot-docs",
                license="CC-BY-3.0",
                license_source="official_docs",
                godot_version=self.version,
                file_path=section,
                metadata={"section": section, "engine_version": self.version},
            )
            items.append(item)
            if len(items) >= max_count:
                break

        return items

    def fetch(self, item: SourceItem) -> SourceItem:
        """Fetches page content from web or mock."""
        def _get():
            self.rate_limiter.acquire(1)
            res = self.session.get(item.source_url, timeout=10)
            res.raise_for_status()
            return res.text

        try:
            content = backoff_retry(_get, max_retries=2, initial_delay=1.0)
            item.raw_content = content if content is not None else ""
        except Exception as e:
            logger.warning("Could not fetch docs from %s: %s (will use placeholder if offline)", item.source_url, e)
            item.raw_content = ""
        return item
