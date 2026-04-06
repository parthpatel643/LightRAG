import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime

import boto3
import jwt
import requests
import yaml
from botocore.exceptions import ClientError
from cacheout import Cache

from .utils import rest_call

# Track the last token update time
last_token_updated_time = datetime.now()
# Create a cache with a default TTL of 50 minutes (3000 seconds)
# This ensures tokens are automatically invalidated after expiry
ttl_seconds = 3000
token_cache = Cache(ttl=ttl_seconds)


# Extend MlAppConfig with additional Kong/OAuth2 configuration
@dataclass
class MlAppConfigExtended:
    app_name: str
    app_version: str
    kong_creds_secret: str | None = None
    kong_kic_creds_secret: str | None = None
    oauth2_tenant_id: str | None = None
    oauth2_token_generation_scope: str | None = None
    oauth2_token_generation_grant_type: str | None = None

    @classmethod
    def from_file(cls, file_path: str) -> "MlAppConfigExtended":
        """
        Load configuration from a YAML file.

        :param file_path: Path to the YAML configuration file
        :return: MlAppConfigExtended instance
        """
        if not os.path.exists(file_path):
            logging.warning(f"Config file not found at {file_path}, using defaults")
            return cls()

        try:
            with open(file_path, "r") as f:
                config_data = yaml.safe_load(f) or {}
            return cls(**config_data)
        except Exception as e:
            logging.warning(
                f"Failed to load config from {file_path}: {e}, using defaults"
            )
            return cls()


# Load config from YAML file placed in the same directory
config_yaml_path = os.path.join(os.path.dirname(__file__), "kong_config.yaml")
config = MlAppConfigExtended.from_file(config_yaml_path)


class KongClient:
    """
    A client to interact with Kong Admin API and generate authentication tokens.
    Supports JWT-based and OIDC/OAuth2-based authentication.
    """

    def __init__(
        self,
        region_name,
        user_secret_manager_name=None,
        jwt_key=None,
        jwt_secret=None,
        authentication_type="jwt",
    ):
        # Initialize instance variables
        self.region_name = region_name
        self.user_secret_manager_name = user_secret_manager_name
        self.jwt_key = jwt_key
        self.jwt_secret = jwt_secret
        self.authentication_type = authentication_type
        self.oauth2_client_id = None
        self.oauth2_client_secret = None

        # Retrieve Kong admin credentials from AWS Secrets Manager
        self.secret_name = config.kong_creds_secret
        self.secret = self.get_secret(self.secret_name, self.region_name)
        self.kong_admin_url = self.secret.get("KONG_ADMIN_URL")
        self.token = self.secret.get("token")

        # Retrieve kic Kong admin credentials from AWS Secrets Manager
        self.kic_secret_name = config.kong_kic_creds_secret
        self.kic_secret = self.get_secret(self.kic_secret_name, self.region_name)
        self.kic_kong_admin_url = self.kic_secret.get("KONG_ADMIN_URL")
        self.kic_token = self.kic_secret.get("token")

        # Retrieve user-specific credentials if user_secret_manager_name is provided
        if self.user_secret_manager_name:
            user_secret = self.get_secret(
                self.user_secret_manager_name, self.region_name
            )
            self.jwt_key = user_secret.get("jwt_key")
            self.jwt_secret = user_secret.get("jwt_secret")
            self.oauth2_client_id = user_secret.get("oauth2_client_id")
            self.oauth2_client_secret = user_secret.get("oauth2_client_secret")

    def get_secret(self, secret_name, region_name):
        """
        Retrieves a secret from AWS Secrets Manager.

        :param secret_name: The name of the secret to retrieve.
        :param region_name: The AWS region where the secret is stored.
        :return: A dictionary containing the secret data, or None if retrieval fails.
        """
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)

        try:
            # Call AWS Secrets Manager to retrieve secret
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        except ClientError as e:
            # Handle missing or invalid secrets
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                raise ValueError(f"Secret '{secret_name}' does not exist.")
            else:
                logging.error(f"Error retrieving secret: {e}")
                raise ValueError(f"Error retrieving secret: {e}")
        else:
            # If secret exists, return its JSON-decoded value
            if "SecretString" in get_secret_value_response:
                return json.loads(get_secret_value_response["SecretString"])
        return None

    def get_existing_consumer_jwt_creds(self, KONG_ADMIN_URL, token, consumer_id):
        # Fetch existing JWT credentials for a given consumer
        url = (
            KONG_ADMIN_URL
            + "core-entities/consumers/"
            + consumer_id
            + "/jwt?sort_desc=1"
        )
        logging.debug("hitting the api to get the existing jwt creds for a consumer")
        response = rest_call(url, token)
        return response.json()

    def get_consumer_details(self, KONG_ADMIN_URL, token, user_cred):
        # Retrieve details for a specific consumer by username/ID
        logging.debug("hitting the api to fetch the consumer id")
        url = KONG_ADMIN_URL + "core-entities/consumers/" + user_cred
        response = rest_call(url, token)
        return response

    def create_consumer_jwt_cred(self, KONG_ADMIN_URL, token, consumer_id):
        # Generate new JWT credentials for a consumer
        logging.debug("hitting the api to generate the jwt creds for a consumer")
        url = KONG_ADMIN_URL + "core-entities/consumers/" + consumer_id + "/jwt"
        response = rest_call(url, token, method_type="POST")
        key = response.json()["key"]
        secret = response.json()["secret"]
        return key, secret

    def generate_consumer_jwt_cred(self, user_cred, kic_flag):
        # Retrieve or create JWT credentials for a consumer
        logging.debug("generating consumer jwt credentials")
        kong_url = self.kong_admin_url
        kong_token = self.token
        if kic_flag == True:
            kong_url = self.kic_kong_admin_url
            kong_token = self.kic_token
        consumer_config_resp = self.get_consumer_details(
            kong_url, kong_token, user_cred
        )

        if consumer_config_resp.status_code == 200:
            consumer_id = consumer_config_resp.json()["id"]
            check_existing_creds = self.get_existing_consumer_jwt_creds(
                kong_url, kong_token, consumer_id
            )["data"]
            if len(check_existing_creds) > 0:
                # Use existing credentials if present
                logging.debug("credentials already exists")
                key = check_existing_creds[0]["key"]
                secret = check_existing_creds[0]["secret"]
            else:
                # Otherwise generate new credentials
                logging.debug("credentials does not exists, generating...")
                key, secret = self.create_consumer_jwt_cred(
                    kong_url, kong_token, consumer_id
                )
            return key, secret
        else:
            # Raise error if consumer lookup failed
            raise Exception(
                f"Request failed with status {consumer_config_resp.status_code}: {consumer_config_resp.text}"
            )

    def generate_jwt_token(
        self, jwt_key, jwt_secret, refresh_token=True, custom_payload=None
    ):
        """
        Generate a JWT token for Kong authentication with caching.

        Args:
            jwt_key: The JWT key (iss claim)
            jwt_secret: The JWT secret for signing
            custom_payload: Optional dict to include additional claims in the token
            refresh_token: Force refresh the token even if cached

        Returns:
            JWT bearer token string
        """
        # Create a unique cache key based on the jwt_key
        cache_key = f"token_{jwt_key}"

        # Return cached token if available and not forcing refresh
        if not refresh_token and cache_key in token_cache:
            logging.debug(f"Using cached token for key {jwt_key}")
            return token_cache.get(cache_key)

        # Generate a new token
        logging.debug(f"Generating new JWT token for key {jwt_key}")
        now = int(time.time())

        # Prepare payload
        payload = {"iss": jwt_key, "exp": now + ttl_seconds}
        if custom_payload is not None and isinstance(custom_payload, dict):
            payload.update(custom_payload)

        # Create the token with the specified TTL
        bearer_token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        # Store in cache with the same TTL
        token_cache.set(cache_key, bearer_token, ttl=ttl_seconds)

        return bearer_token

    def generate_oauth2_token(self, client_id, client_secret, refresh_token=False):
        # Create a unique cache key based on the client_id
        cache_key = f"token_{client_id}"

        # Return cached token if available and not forcing refresh
        if not refresh_token and cache_key in token_cache:
            logging.debug("Using cached token for OAuth2 client.")
            return token_cache.get(cache_key)

        # generating the oauth2 token
        logging.info("generating oauth2 token")
        url = f"https://login.microsoftonline.com/{config.oauth2_tenant_id}/oauth2/v2.0/token"

        # Construct payload for client credentials flow
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": config.oauth2_token_generation_scope,
            "grant_type": config.oauth2_token_generation_grant_type,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            logging.info("Got successful response, fetching the token.")
            data = response.json()
            token = data["access_token"]

            # Store in cache with the same TTL
            token_cache.set(cache_key, token, ttl=ttl_seconds)

            return token
        else:
            # Raise error if token request failed
            raise Exception(
                f"Token generation request failed for {client_id} with status {response.status_code}: {response.text}"
            )

    def generate_token(
        self, jwt_key=None, jwt_secret=None, refresh_token=True, custom_payload=None
    ):
        """
        Generate a token for Kong authentication with caching based on the token type mentioned.

        Args:
            jwt_key: The key required for generating the jwt token
            jwt_secret: the secret required for generating the token
            refresh_token: Force refresh the token even if cached
            custom_payload: Optional dict to include additional claims in the JWT token

        Returns:
             bearer token string

        Raises:
            ValueError: If aws_secret_name is empty or None
            ValueError: If jwt_key and jwt_secret are empty or None in the secret in case of jwt authentication.
            ValueError: If oauth2_client_id and oauth2_client_secret is empty or None in the secret in case of oidc authentication.
            ValueError: If the value of authentication type provided is not correct.
        """
        # Validate input
        if self.authentication_type == "jwt":
            if jwt_key and jwt_secret:
                # update instance variables if provided directly
                self.jwt_key = jwt_key
                self.jwt_secret = jwt_secret

            if not self.jwt_key or not self.jwt_secret:
                error_msg = "JWT key and secret must be provided either directly or in the secret while creating KongClient object instance."
                logging.debug(error_msg)
                raise ValueError(error_msg)

            # call the method to generate token, passing custom_payload
            token = self.generate_jwt_token(
                self.jwt_key,
                self.jwt_secret,
                custom_payload=custom_payload,
                refresh_token=refresh_token,
            )
        elif self.authentication_type == "oidc":
            # generating the oauth2 token for oidc authentication

            # Validate retrieved values
            if not self.oauth2_client_id or not self.oauth2_client_secret:
                error_msg = (
                    "OAuth2 client id and secret must be provided in the secret."
                )
                logging.debug(error_msg)
                raise ValueError(error_msg)

            if custom_payload:
                logging.warning(
                    "Custom payload is ignored for OIDC/OAuth2 token generation."
                )

            token = self.generate_oauth2_token(
                self.oauth2_client_id, self.oauth2_client_secret, refresh_token
            )

        # Invalid auth type
        else:
            error_msg = (
                "Provided authentication type is not valid. valid types: (jwt, oidc)"
            )
            logging.debug(error_msg)
            raise ValueError(error_msg)

        return token
