import logging

import requests


def rest_call(url, token, api_headers=None, payload=None, method_type="GET"):
    if api_headers is None:
        api_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
    logging.info(f"hitting the api with {url} to get the response")
    if payload is not None and method_type == "POST":
        response = requests.request(method_type, url, data=payload, headers=api_headers)
    else:
        response = requests.request(method_type, url, headers=api_headers)
    logging.debug(f"recieved the following response :{response}")
    if response.status_code == 200 or response.status_code == 201:
        return response
    else:
        raise Exception(
            f"Request failed with status {response.status_code}: {response.text}"
        )
