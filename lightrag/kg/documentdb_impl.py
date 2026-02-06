"""
AWS DocumentDB storage implementations.

DocumentDB is MongoDB-compatible. This module provides convenience wrappers
that map DOCUMENTDB_* environment variables to MONGO_* variables, allowing
users to use DocumentDB with explicit environment variable names.

Recommended Usage:
    Since DocumentDB is fully MongoDB-compatible, you can simply use:
    - MongoKVStorage
    - MongoDocStatusStorage
    - MongoVectorDBStorage

    And set MONGO_URI with your DocumentDB connection string.

    These DocumentDB classes are provided for users who prefer separate
    environment variable names (DOCUMENTDB_ENDPOINT, etc.) for clarity.
"""

import os

from ..utils import logger

# Import MongoDB implementations since DocumentDB is MongoDB-compatible
try:
    from .mongo_impl import (
        MongoDocStatusStorage as _MongoDocStatusStorage,
    )
    from .mongo_impl import (
        MongoKVStorage as _MongoKVStorage,
    )
    from .mongo_impl import (
        MongoVectorDBStorage as _MongoVectorDBStorage,
    )

    def _map_documentdb_env_to_mongo():
        """Map DocumentDB environment variables to MongoDB variables for compatibility."""
        if os.environ.get("DOCUMENTDB_ENDPOINT"):
            endpoint = os.environ.get("DOCUMENTDB_ENDPOINT")
            port = os.environ.get("DOCUMENTDB_PORT", "27017")
            username = os.environ.get("DOCUMENTDB_USERNAME", "")
            password = os.environ.get("DOCUMENTDB_PASSWORD", "")
            ssl = os.environ.get("DOCUMENTDB_SSL", "true").lower() == "true"

            # Build MongoDB-compatible URI
            if username and password:
                uri = f"mongodb://{username}:{password}@{endpoint}:{port}/"
            else:
                uri = f"mongodb://{endpoint}:{port}/"

            # Add SSL parameter if needed
            if ssl:
                uri += "?tls=true&tlsAllowInvalidCertificates=true"

            os.environ["MONGO_URI"] = uri
            logger.debug("Mapped DOCUMENTDB_ENDPOINT to MONGO_URI")

        if os.environ.get("DOCUMENTDB_DATABASE"):
            os.environ["MONGO_DATABASE"] = os.environ["DOCUMENTDB_DATABASE"]
            logger.debug("Mapped DOCUMENTDB_DATABASE to MONGO_DATABASE")

        if os.environ.get("DOCUMENTDB_WORKSPACE"):
            os.environ["MONGODB_WORKSPACE"] = os.environ["DOCUMENTDB_WORKSPACE"]
            logger.debug("Mapped DOCUMENTDB_WORKSPACE to MONGODB_WORKSPACE")

    # Map environment variables before creating classes
    _map_documentdb_env_to_mongo()

    # Create aliases - these are the same as MongoDB classes but with DocumentDB naming
    # Users can use these with DOCUMENTDB_* environment variables
    DocumentDBKVStorage = _MongoKVStorage
    DocumentDBDocStatusStorage = _MongoDocStatusStorage
    DocumentDBVectorDBStorage = _MongoVectorDBStorage

    __all__ = [
        "DocumentDBKVStorage",
        "DocumentDBDocStatusStorage",
        "DocumentDBVectorDBStorage",
    ]

except ImportError as e:
    logger.warning(f"DocumentDB storage not available: {e}")
    logger.warning("Install pymongo to use DocumentDB storage: pip install pymongo")

    # Provide stub classes that will raise errors if instantiated
    class DocumentDBKVStorage:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "DocumentDB storage requires pymongo. Install it with: pip install pymongo"
            )

    class DocumentDBDocStatusStorage:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "DocumentDB storage requires pymongo. Install it with: pip install pymongo"
            )

    class DocumentDBVectorDBStorage:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "DocumentDB storage requires pymongo. Install it with: pip install pymongo"
            )

    __all__ = [
        "DocumentDBKVStorage",
        "DocumentDBDocStatusStorage",
        "DocumentDBVectorDBStorage",
    ]
