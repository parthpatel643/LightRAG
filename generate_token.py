# This method should generate a new bearer token every 60 minute and provide
# The below code assumes you have access to gen-ai sdk
import time

import requests

_token_cache = {"token": None, "timestamp": 0}


def provide_bearer_token(base_url: str = "https://mars-llm-proxy-dev.ual.com"):
    current_time = time.time()
    # Cache for 30 minutes (1800 seconds)
    if _token_cache["token"] and (current_time - _token_cache["timestamp"] < 1800):
        return _token_cache["token"]

    # Refer the separate example shared for generating bearer token.
    request_body = {
        "key": "dhR1sgZti4EZ4QtbMxBRrAzF99YxNrCJD68OfB4BKsgDALsqaSyKOs3Jg5U3uQX/+fj8MuII0ofmBEAPsowt3pSZsgMw7XXSZeq5DVJxrHdb*EA158QQXDJCZi9RWKCCwMQ==*7+Zyo/EDha4lGLcWxIS0dg==*vCGI7G0EbgwkToOOd9POjw=="
    }
    response = requests.post(
        url=f"{base_url}/generatetoken", json=request_body, verify=False
    )
    proxy_token = response.json()["access_token"]

    new_token = {"Authorization": f"Bearer {proxy_token}"}

    _token_cache["token"] = new_token
    _token_cache["timestamp"] = time.time()

    return new_token
