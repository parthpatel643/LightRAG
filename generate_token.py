# This method should generate a new bearer token every 60 minute and provide
# The below code assumes you have access to gen-ai sdk
import time
import os
import requests

_token_cache = {"token": None, "timestamp": 0}


def provide_bearer_token():
    current_time = time.time()
    # Cache for 30 minutes (1800 seconds)
    if _token_cache["token"] and (current_time - _token_cache["timestamp"] < 1800):
        return _token_cache["token"]

    # Refer the separate example shared for generating bearer token.
    request_body = {
        "key": os.getenv("TOKEN_BINDING_API_KEY")
    }
    response = requests.post(
        url=os.getenv("TOKEN_BINDING_HOST"), json=request_body, verify=False
    )
    proxy_token = response.json()["access_token"]

    new_token = {"Authorization": f"Bearer {proxy_token}"}

    _token_cache["token"] = new_token
    _token_cache["timestamp"] = time.time()

    return new_token
