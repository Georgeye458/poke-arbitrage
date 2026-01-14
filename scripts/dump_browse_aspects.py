import asyncio
import json

import httpx

from app.api.ebay_auth import ebay_auth
from app.config import settings


async def main():
    token = await ebay_auth.get_client_credentials_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_AU",
        "Content-Type": "application/json",
    }

    params = {
        "q": "psa 10 pokemon card",
        "category_ids": "183454",
        "filter": "buyingOptions:{FIXED_PRICE}",
        "aspect_filter": "categoryId:183454,Language:{English}",
        "fieldgroups": "ASPECT_REFINEMENTS",
        "limit": 10,
        "offset": 0,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.ebay_api_base_url}/buy/browse/v1/item_summary/search",
            headers=headers,
            params=params,
            timeout=30.0,
        )
        print("status", resp.status_code)
        data = resp.json()
        refinement = data.get("refinement", {}) or {}
        aspects = refinement.get("aspectDistributions") or []
        names = [a.get("localizedAspectName") or a.get("aspectName") for a in aspects]
        print("aspect_names", names)

        want = {"Graded", "Grade", "Professional Grader"}
        for a in aspects:
            name = a.get("localizedAspectName") or a.get("aspectName")
            if name in want:
                vals = a.get("aspectValueDistributions") or []
                top = [v.get("localizedAspectValue") for v in vals[:30]]
                print(f\"{name}_values\", top)


if __name__ == "__main__":
    asyncio.run(main())

