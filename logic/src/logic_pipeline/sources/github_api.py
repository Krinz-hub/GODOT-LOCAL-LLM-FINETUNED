"""GitHub API connector for Godot repository discovery."""

import os
from typing import Any, Dict, List, Optional
import requests
from logic_pipeline.sources.base import BaseSource, SourceItem
from logic_pipeline.rate_limit import RateLimiter, backoff_retry
from logic_pipeline.logging_config import get_logger

logger = get_logger("sources.github")


class GitHubSource(BaseSource):
    """Discovers Godot repositories using the GitHub Search API."""

    def __init__(
        self,
        queries: List[str],
        token_env_var: str = "GITHUB_TOKEN",
        min_stars: int = 5,
        max_repos: int = 20,
        allowed_licenses: Optional[List[str]] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        super().__init__(name="github")
        self.queries = queries
        self.token = os.environ.get(token_env_var, "")
        self.min_stars = min_stars
        self.max_repos = max_repos
        self.allowed_licenses = allowed_licenses or ["MIT", "Apache-2.0", "BSD-3-Clause", "CC0-1.0"]
        self.rate_limiter = rate_limiter or RateLimiter(requests_per_minute=30)
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GodotLogicAgent-Crawler/1.0",
        })

    def _search_repositories(self, query: str) -> List[Dict[str, Any]]:
        """Queries GitHub repository search API with backoff."""
        url = "https://api.github.com/search/repositories"
        params = {"q": f"{query} stars:>={self.min_stars}", "sort": "stars", "order": "desc", "per_page": 30}

        def _do_request():
            self.rate_limiter.acquire(1)
            response = self.session.get(url, params=params, timeout=15)
            if response.status_code == 403:
                logger.warning("GitHub rate limit hit: %s", response.text)
                return []
            response.raise_for_status()
            return response.json().get("items", [])

        try:
            res = backoff_retry(_do_request, max_retries=2, initial_delay=2.0)
            return res if res is not None else []
        except Exception as e:
            logger.warning("GitHub search failed for query '%s': %s", query, e)
            return []

    def discover(self, limit: Optional[int] = None) -> List[SourceItem]:
        """Discovers repositories matching criteria."""
        discovered: List[SourceItem] = []
        max_count = limit or self.max_repos
        seen_repos = set()

        for query in self.queries:
            repos = self._search_repositories(query)
            for repo in repos:
                full_name = repo.get("full_name")
                if not full_name or full_name in seen_repos:
                    continue
                seen_repos.add(full_name)

                # Check license
                lic_data = repo.get("license") or {}
                spdx_id = lic_data.get("spdx_id", "NOASSERTION")
                if self.allowed_licenses and spdx_id not in self.allowed_licenses and spdx_id != "NOASSERTION":
                    logger.debug("Skipping %s: license %s not in allowed list", full_name, spdx_id)
                    continue

                item = SourceItem(
                    item_id=f"github:{full_name}",
                    source_type="github",
                    source_url=repo.get("html_url", f"https://github.com/{full_name}"),
                    repository=full_name,
                    commit_hash=repo.get("default_branch", "main"),
                    license=spdx_id,
                    license_source="github_api",
                    godot_version="Godot 4.x",
                    metadata={
                        "stars": repo.get("stargazers_count", 0),
                        "description": repo.get("description", ""),
                        "clone_url": repo.get("clone_url"),
                    },
                )
                discovered.append(item)
                if len(discovered) >= max_count:
                    return discovered

        return discovered

    def fetch(self, item: SourceItem) -> SourceItem:
        """Fetches repository metadata or delegates to git clone."""
        # Detailed file fetching is handled via git shallow clone or raw API
        return item
