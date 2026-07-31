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
cache_ttl_seconds = 3000
# Generate token valid for 60 minutes while the cache is valid for 50 minutes
# This would provide a safe 10 min buffer
token_ttl_seconds = 3600
token_cache = Cache(ttl=cache_ttl_seconds)


# Extend MlAppConfig with additional Kong/OAuth2 configuration
@dataclass
class MlAppConfigExtended:
    kong_creds_secret: str | None = None
    kong_kic_creds_secret: str | None = None
    oauth2_tenant_id: str | None = None  # Legacy field for backward compatibility
    oauth2_global_test_tenent_id: str | None = (
        None  # Legacy field for backward compatibility
    )
    oauth2_tenants: dict | None = None  # New tenant-specific configuration
    default_oauth2_tenant_type: str = "global"  # Default tenant type
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

    def generate_consumer_jwt_cred(self, user_cred, kic_flag, app_env="dev"):
        # Retrieve or create JWT credentials for a consumer
        logging.debug("generating consumer jwt credentials")
        if app_env.lower() in ["stg", "stage"]:
            app_env = "STG"
        elif app_env.lower() in ["prd", "prod"]:
            app_env = "PRD"
        elif app_env.lower() in ["qa"]:
            app_env = "QA"
        # Try env-specific key first (e.g. KONG_ADMIN_URL_DEV), fall back to KONG_ADMIN_URL
        env_key = f"KONG_ADMIN_URL_{app_env.upper()}"
        kong_url = self.kic_secret.get(env_key) or self.secret.get("KONG_ADMIN_URL")
        if not kong_url:
            raise ValueError(
                f"Neither '{env_key}' nor 'KONG_ADMIN_URL' found in secret '{self.secret_name}'. "
                f"Ensure the secret contains a key for the requested environment."
            )
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
        payload = {"iss": jwt_key, "exp": now + token_ttl_seconds}
        if custom_payload is not None and isinstance(custom_payload, dict):
            payload.update(custom_payload)

        # Create the token with the specified TTL
        bearer_token = jwt.encode(payload, jwt_secret, algorithm="HS256")

        # Store in cache with the same TTL
        token_cache.set(cache_key, bearer_token, ttl=cache_ttl_seconds)

        return bearer_token

    def generate_oauth2_token(
        self, client_id, client_secret, refresh_token=False, tenant_type=None
    ):
        """
        Generate OAuth2 token with tenant-specific configuration.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            refresh_token: Force refresh the token even if cached
            tenant_type: The tenant type to use (global, global_test, etc.).
                        If None, uses default_oauth2_tenant_type from config

        Returns:
            Access token string

        Raises:
            ValueError: If tenant_type is invalid
            Exception: If token generation request fails
        """
        # Resolve tenant type with fallback to default
        resolved_tenant_type = tenant_type or config.default_oauth2_tenant_type

        # Get tenant-specific OAuth2 tenant ID
        if config.oauth2_tenants:
            tenant_config = config.oauth2_tenants.get(resolved_tenant_type)
            if not tenant_config:
                raise ValueError(
                    f"Invalid tenant_type: {resolved_tenant_type}. "
                    f"Valid options: {list(config.oauth2_tenants.keys())}"
                )
            oauth2_tenant_id = tenant_config.get("tenant_id")
            if not oauth2_tenant_id:
                raise ValueError(
                    f"tenant_id not found in config for tenant: {resolved_tenant_type}"
                )
        else:
            # Backward compatibility: use legacy config keys if oauth2_tenants is not defined
            if resolved_tenant_type == "global":
                oauth2_tenant_id = config.oauth2_tenant_id
            elif resolved_tenant_type == "global_test":
                oauth2_tenant_id = config.oauth2_global_test_tenent_id
            else:
                raise ValueError(f"Unknown tenant type: {resolved_tenant_type}")

            if not oauth2_tenant_id:
                raise ValueError(
                    f"oauth2_tenant_id not found in config for tenant: {resolved_tenant_type}"
                )

        # Create a unique cache key based on client_id and tenant_type
        cache_key = f"token_{client_id}_{resolved_tenant_type}"

        # Return cached token if available and not forcing refresh
        if not refresh_token and cache_key in token_cache:
            logging.debug(
                f"Using cached token for OAuth2 client {client_id[:4]}****, tenant {resolved_tenant_type}"
            )
            return token_cache.get(cache_key)

        # Generate the oauth2 token
        logging.info(f"Generating oauth2 token for tenant type: {resolved_tenant_type}")
        url = f"https://login.microsoftonline.com/{oauth2_tenant_id}/oauth2/v2.0/token"

        # Construct payload for client credentials flow
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": f"{client_id}/.default",
            "grant_type": config.oauth2_token_generation_grant_type,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            logging.info(
                f"OAuth2 token fetched successfully for tenant type: {resolved_tenant_type}"
            )
            data = response.json()
            token = data["access_token"]

            # Store in cache with the same TTL
            token_cache.set(cache_key, token, ttl=cache_ttl_seconds)

            return token
        else:
            # Check for specific error and retry with config scope if needed
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    if (
                        error_data.get("error") == "invalid_grant"
                        and payload["scope"] == f"{client_id}/.default"
                        and config.oauth2_token_generation_scope
                    ):
                        logging.info(
                            "Retrying OAuth2 token generation with configured scope from config."
                        )
                        payload["scope"] = config.oauth2_token_generation_scope
                        response = requests.request(
                            "POST", url, headers=headers, data=payload
                        )
                        if response.status_code == 200:
                            data = response.json()
                            token = data["access_token"]
                            token_cache.set(cache_key, token, ttl=cache_ttl_seconds)
                            return token
                        else:
                            raise Exception(
                                f"Retry with config scope failed with status {response.status_code}: {response.text}"
                            )
                    else:
                        raise Exception(
                            f"Token generation failed with status {response.status_code}: {response.text}"
                        )
                except Exception as e:
                    raise Exception(f"Error parsing OAuth2 error response: {e}")
            else:
                # Raise error if token request failed
                raise Exception(
                    f"Token generation request failed for {client_id} with status {response.status_code}: {response.text}"
                )

    def generate_token(
        self,
        jwt_key=None,
        jwt_secret=None,
        refresh_token=False,
        custom_payload=None,
        tenant_type=None,
    ):
        """
        Generate a token for Kong authentication with caching based on the token type mentioned.

        Args:
            jwt_key: The key required for generating the jwt token
            jwt_secret: the secret required for generating the token
            refresh_token: Force refresh the token even if cached
            custom_payload: Optional dict to include additional claims in the JWT token
            tenant_type: The tenant type to use for OAuth2 tokens (global, global_test, etc.).
                        If None, uses default_oauth2_tenant_type from config.
                        Ignored for JWT authentication.

        Returns:
             bearer token string

        Raises:
            ValueError: If aws_secret_name is empty or None
            ValueError: If jwt_key and jwt_secret are empty or None in the secret in case of jwt authentication.
            ValueError: If oauth2_client_id and oauth2_client_secret is empty or None in the secret in case of oidc authentication.
            ValueError: If the value of authentication type provided is not correct.
            ValueError: If tenant_type is invalid for OAuth2 authentication.
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
                self.oauth2_client_id,
                self.oauth2_client_secret,
                refresh_token,
                tenant_type=tenant_type,
            )

        # Invalid auth type
        else:
            error_msg = (
                "Provided authentication type is not valid. valid types: (jwt, oidc)"
            )
            logging.debug(error_msg)
            raise ValueError(error_msg)

        return token
