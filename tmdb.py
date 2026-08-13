import time

import aiohttp

API = "https://api.themoviedb.org/3"
IMAGE = "https://image.tmdb.org/t/p/w500"


class TMDB:
    def __init__(self, api_key: str, cache_ttl: int = 3600, cache_size: int = 512):
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self.cache = {}
        self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str, **params):
        params = {**params, "api_key": self.api_key, "language": "ru-RU"}
        key = (path, tuple(sorted(params.items())))
        now = time.monotonic()
        hit = self.cache.get(key)
        if hit and now - hit[0] < self.cache_ttl:
            return hit[1]
        async with self.session.get(f"{API}{path}", params=params) as resp:
            data = await resp.json()
        self.cache[key] = (now, data)
        if len(self.cache) > self.cache_size:
            expired = [k for k, (t, _) in self.cache.items() if now - t >= self.cache_ttl]
            for k in expired:
                del self.cache[k]
            while len(self.cache) > self.cache_size:
                self.cache.pop(next(iter(self.cache)))
        return data

    async def search(self, media_type: str, query: str, page: int = 1):
        return await self._get(f"/search/{media_type}", query=query, page=page, include_adult="false")

    async def details(self, media_type: str, item_id: int):
        return await self._get(f"/{media_type}/{item_id}")

    async def person_credits(self, person_id: int):
        return await self._get(f"/person/{person_id}/combined_credits")

    async def credits(self, media_type: str, item_id: int):
        return await self._get(f"/{media_type}/{item_id}/credits")

    async def similar(self, media_type: str, item_id: int):
        return await self._get(f"/{media_type}/{item_id}/similar")

    async def recommendations(self, media_type: str, item_id: int):
        return await self._get(f"/{media_type}/{item_id}/recommendations")

    async def fetch_image(self, path: str) -> bytes | None:
        if not path:
            return None
        try:
            async with self.session.get(
                f"{IMAGE}{path}", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception:
            return None
        return None

    @staticmethod
    def name(item: dict, media_type: str) -> str:
        if media_type == "movie":
            return item.get("title") or item.get("original_title") or "?"
        return item.get("name") or item.get("original_name") or "?"

    @staticmethod
    def year(item: dict, media_type: str) -> str:
        date = item.get("release_date") or item.get("first_air_date") or ""
        return date[:4]
