import os

import httpx
from openai import AsyncOpenAI


async def check_openai_api() -> bool:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return False
    try:
        client = AsyncOpenAI(api_key=api_key, timeout=10.0, max_retries=0)
        await client.models.list()
        return True
    except Exception:
        return False


async def check_elevenlabs_api() -> bool:
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": api_key},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def check_all_apis() -> dict[str, dict[str, bool | str]]:
    from .news_service import check_news_api_key

    results = await asyncio_gather_safe(
        ("news", check_news_api_key()),
        ("openai", check_openai_api()),
        ("elevenlabs", check_elevenlabs_api()),
    )

    status: dict[str, dict[str, bool | str]] = {}
    for name, ok in results:
        status[name] = {
            "available": ok,
            "status": "up" if ok else "down",
        }
    return status


async def asyncio_gather_safe(*tasks):
    import asyncio

    results = await asyncio.gather(
        *(t[1] for t in tasks),
        return_exceptions=True,
    )
    return [
        (tasks[i][0], False if isinstance(results[i], BaseException) else results[i])
        for i in range(len(tasks))
    ]
