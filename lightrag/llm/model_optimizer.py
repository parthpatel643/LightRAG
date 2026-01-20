"""
Model-specific optimizations for different LLM providers.

This module provides optimizations and best practices for each LLM provider
supported by LightRAG, improving performance, cost efficiency, and quality.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from ..utils import logger


class ModelTier(str, Enum):
    """LLM model categorization by capability and cost."""
    
    SMALL = "small"      # Fast, cheap models best for simple tasks (summarization, entity extraction)
    MEDIUM = "medium"    # Balanced models for most RAG tasks
    LARGE = "large"      # High-capability models for complex reasoning tasks
    SPECIALIZED = "specialized"  # Domain-specific models optimized for particular use cases


class TaskType(str, Enum):
    """Types of tasks performed in LightRAG workflows."""
    
    ENTITY_EXTRACTION = "entity_extraction"
    RELATION_EXTRACTION = "relation_extraction"
    SUMMARIZATION = "summarization"
    QUERY_ANSWERING = "query_answering"
    RERANKING = "reranking"
    SCHEMA_INFERENCE = "schema_inference"
    CONTENT_MODERATION = "content_moderation"


@dataclass
class ModelOptimizationConfig:
    """Configuration for model-specific optimizations."""
    
    # Model selection strategy
    use_tiered_models: bool = True  # Use different model tiers for different tasks
    fallback_on_error: bool = True  # Try fallback models if primary model fails
    
    # Performance optimizations
    enable_batching: bool = True  # Batch similar requests when possible
    max_batch_size: int = 20  # Maximum batch size for batched requests
    max_concurrency: int = 8  # Maximum concurrent requests to model provider
    
    # Quality/cost tradeoffs
    enable_caching: bool = True  # Cache responses to avoid redundant model calls
    cache_ttl_seconds: int = 86400 * 30  # Cache TTL (30 days default)
    
    # Provider-specific settings
    provider_settings: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Task-specific model assignments
    task_model_map: Dict[TaskType, Dict[ModelTier, str]] = field(default_factory=dict)


class ModelOptimizer:
    """
    Optimize LLM usage for different providers and tasks.
    
    This class provides optimizations specific to each LLM provider supported by
    LightRAG, including:
    
    1. Task-appropriate model selection
    2. Provider-specific parameter tuning
    3. Cost optimization techniques
    4. Performance improvements
    """
    
    def __init__(self, config: Optional[ModelOptimizationConfig] = None):
        """
        Initialize the model optimizer.
        
        Args:
            config: Configuration for model optimizations
        """
        self.config = config or ModelOptimizationConfig()
        self._initialized_providers = set()
        
    def initialize_provider(self, provider: str) -> None:
        """
        Initialize optimizations for a specific provider.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic', 'bedrock')
        """
        if provider in self._initialized_providers:
            return
            
        provider_lower = provider.lower()
        
        # Set up default provider settings if not already configured
        if provider_lower not in self.config.provider_settings:
            self.config.provider_settings[provider_lower] = {}
            
        # Initialize provider-specific optimizations
        if provider_lower == "openai":
            self._init_openai_optimizations()
        elif provider_lower == "anthropic":
            self._init_anthropic_optimizations()
        elif provider_lower == "cohere":
            self._init_cohere_optimizations()
        elif provider_lower == "bedrock":
            self._init_bedrock_optimizations()
        elif provider_lower == "google":
            self._init_google_optimizations()
        elif provider_lower == "ollama":
            self._init_ollama_optimizations()
        
        # Initialize task-model mapping if not already configured
        if not self.config.task_model_map:
            self._init_default_task_models(provider_lower)
            
        self._initialized_providers.add(provider_lower)
        logger.info(f"Initialized model optimizations for {provider}")
        
    def _init_openai_optimizations(self) -> None:
        """Initialize OpenAI-specific optimizations."""
        settings = self.config.provider_settings["openai"]
        
        # Default settings if not specified
        settings.setdefault("retry_on_rate_limit", True)
        settings.setdefault("max_retries", 3)
        settings.setdefault("retry_base_delay", 1.0)
        settings.setdefault("retry_max_delay", 60.0)
        settings.setdefault("use_json_mode", True)  # Use JSON mode for structured outputs
        settings.setdefault("response_format", {"type": "json"})  # Default to JSON responses
        
    def _init_anthropic_optimizations(self) -> None:
        """Initialize Anthropic-specific optimizations."""
        settings = self.config.provider_settings["anthropic"]
        
        # Default settings if not specified
        settings.setdefault("retry_on_rate_limit", True)
        settings.setdefault("max_retries", 3)
        settings.setdefault("retry_base_delay", 1.0)
        settings.setdefault("retry_max_delay", 60.0)
        settings.setdefault("use_tool_system", True)  # Use tool system for structured outputs
        
    def _init_cohere_optimizations(self) -> None:
        """Initialize Cohere-specific optimizations."""
        settings = self.config.provider_settings["cohere"]
        
        # Default settings if not specified
        settings.setdefault("retry_on_rate_limit", True)
        settings.setdefault("max_retries", 3)
        settings.setdefault("connectors_enabled", False)  # Disable connectors by default
        
    def _init_bedrock_optimizations(self) -> None:
        """Initialize AWS Bedrock-specific optimizations."""
        settings = self.config.provider_settings["bedrock"]
        
        # Default settings if not specified
        settings.setdefault("use_regional_endpoints", True)
        settings.setdefault("preferred_region", None)  # Use client's default region
        settings.setdefault("streaming_mode", "event_stream")  # Use event stream for streaming
        
    def _init_google_optimizations(self) -> None:
        """Initialize Google AI (Gemini)-specific optimizations."""
        settings = self.config.provider_settings["google"]
        
        # Default settings if not specified
        settings.setdefault("retry_on_rate_limit", True)
        settings.setdefault("max_retries", 3)
        settings.setdefault("safety_settings", {})  # Default safety settings
        
    def _init_ollama_optimizations(self) -> None:
        """Initialize Ollama-specific optimizations."""
        settings = self.config.provider_settings["ollama"]
        
        # Default settings if not specified
        settings.setdefault("num_gpu", 1)  # Number of GPUs to use
        settings.setdefault("num_thread", 4)  # Number of CPU threads to use
        settings.setdefault("use_mlock", True)  # Lock model in RAM
        
    def _init_default_task_models(self, provider: str) -> None:
        """
        Initialize default task-model mappings for a provider.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
        """
        # Initialize task model map if empty
        if not self.config.task_model_map:
            for task in TaskType:
                self.config.task_model_map[task] = {}
                
        # Set up provider-specific model mappings
        if provider == "openai":
            # OpenAI model mappings
            self.config.task_model_map[TaskType.ENTITY_EXTRACTION][ModelTier.SMALL] = "gpt-3.5-turbo"
            self.config.task_model_map[TaskType.ENTITY_EXTRACTION][ModelTier.MEDIUM] = "gpt-4-turbo"
            self.config.task_model_map[TaskType.ENTITY_EXTRACTION][ModelTier.LARGE] = "gpt-4"
            
            self.config.task_model_map[TaskType.RELATION_EXTRACTION][ModelTier.SMALL] = "gpt-3.5-turbo"
            self.config.task_model_map[TaskType.RELATION_EXTRACTION][ModelTier.MEDIUM] = "gpt-4-turbo"
            self.config.task_model_map[TaskType.RELATION_EXTRACTION][ModelTier.LARGE] = "gpt-4"
            
            self.config.task_model_map[TaskType.SUMMARIZATION][ModelTier.SMALL] = "gpt-3.5-turbo"
            self.config.task_model_map[TaskType.SUMMARIZATION][ModelTier.MEDIUM] = "gpt-3.5-turbo"
            self.config.task_model_map[TaskType.SUMMARIZATION][ModelTier.LARGE] = "gpt-4-turbo"
            
            self.config.task_model_map[TaskType.QUERY_ANSWERING][ModelTier.SMALL] = "gpt-3.5-turbo"
            self.config.task_model_map[TaskType.QUERY_ANSWERING][ModelTier.MEDIUM] = "gpt-4-turbo"
            self.config.task_model_map[TaskType.QUERY_ANSWERING][ModelTier.LARGE] = "gpt-4"
            
        elif provider == "anthropic":
            # Anthropic model mappings
            self.config.task_model_map[TaskType.ENTITY_EXTRACTION][ModelTier.SMALL] = "claude-instant-1.2"
            self.config.task_model_map[TaskType.ENTITY_EXTRACTION][ModelTier.MEDIUM] = "claude-3-haiku"
            self.config.task_model_map[TaskType.ENTITY_EXTRACTION][ModelTier.LARGE] = "claude-3-opus"
            
            self.config.task_model_map[TaskType.RELATION_EXTRACTION][ModelTier.SMALL] = "claude-instant-1.2"
            self.config.task_model_map[TaskType.RELATION_EXTRACTION][ModelTier.MEDIUM] = "claude-3-haiku"
            self.config.task_model_map[TaskType.RELATION_EXTRACTION][ModelTier.LARGE] = "claude-3-opus"
            
            self.config.task_model_map[TaskType.SUMMARIZATION][ModelTier.SMALL] = "claude-3-haiku"
            self.config.task_model_map[TaskType.SUMMARIZATION][ModelTier.MEDIUM] = "claude-3-sonnet"
            self.config.task_model_map[TaskType.SUMMARIZATION][ModelTier.LARGE] = "claude-3-opus"
            
            self.config.task_model_map[TaskType.QUERY_ANSWERING][ModelTier.SMALL] = "claude-3-haiku"
            self.config.task_model_map[TaskType.QUERY_ANSWERING][ModelTier.MEDIUM] = "claude-3-sonnet"
            self.config.task_model_map[TaskType.QUERY_ANSWERING][ModelTier.LARGE] = "claude-3-opus"
            
    def get_optimal_model(
        self, 
        provider: str, 
        task: TaskType, 
        tier: Optional[ModelTier] = None,
        context_length: Optional[int] = None,
    ) -> str:
        """
        Get the optimal model for a specific task and provider.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            task: Type of task to perform
            tier: Model tier to use (optional, defaults to MEDIUM)
            context_length: Required context length (optional)
            
        Returns:
            Model name for the given task and tier
            
        Raises:
            ValueError: If no suitable model is found
        """
        # Initialize provider if needed
        provider_lower = provider.lower()
        if provider_lower not in self._initialized_providers:
            self.initialize_provider(provider_lower)
            
        # Default to medium tier if not specified
        tier = tier or ModelTier.MEDIUM
        
        # Get model for task and tier
        task_models = self.config.task_model_map.get(task, {})
        model = task_models.get(tier)
        
        if not model:
            # Fall back to general model if task-specific not found
            if provider_lower == "openai":
                model = "gpt-4-turbo" if tier == ModelTier.LARGE else "gpt-3.5-turbo"
            elif provider_lower == "anthropic":
                if tier == ModelTier.LARGE:
                    model = "claude-3-opus"
                elif tier == ModelTier.MEDIUM:
                    model = "claude-3-sonnet"
                else:
                    model = "claude-3-haiku"
            elif provider_lower == "cohere":
                model = "command" if tier == ModelTier.LARGE else "command-light"
            else:
                raise ValueError(f"No model found for provider {provider} and tier {tier}")
                
        # Check context length requirements
        if context_length:
            # Adjust model based on context requirements
            if provider_lower == "openai" and context_length > 8192 and "gpt-3.5" in model:
                # Switch to model with larger context
                model = "gpt-4-turbo"
            elif provider_lower == "anthropic" and context_length > 100000:
                # Claude 3 models have 200K context
                model = "claude-3-opus"
                
        return model
        
    def get_optimal_parameters(
        self,
        provider: str,
        task: TaskType,
        model: str,
    ) -> Dict[str, Any]:
        """
        Get optimal parameters for a specific model and task.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            task: Type of task to perform
            model: Model name
            
        Returns:
            Dictionary of optimal parameters for the model
        """
        # Initialize provider if needed
        provider_lower = provider.lower()
        if provider_lower not in self._initialized_providers:
            self.initialize_provider(provider_lower)
            
        # Start with provider settings
        params = self.config.provider_settings.get(provider_lower, {}).copy()
        
        # Add task-specific parameters
        if task == TaskType.ENTITY_EXTRACTION:
            params.update({
                "temperature": 0.0,  # Lower temperature for deterministic extraction
                "top_p": 1.0,        # Disable nucleus sampling for deterministic output
                "max_tokens": 2048,  # Reasonable limit for entity extraction
            })
            
            # Provider-specific optimizations
            if provider_lower == "openai":
                params.update({
                    "response_format": {"type": "json"},  # Force JSON output
                })
                
        elif task == TaskType.RELATION_EXTRACTION:
            params.update({
                "temperature": 0.1,  # Slightly higher for relationship diversity
                "top_p": 0.95,       # Slight nucleus sampling for better relationship diversity
                "max_tokens": 2048,  # Reasonable limit for relation extraction
            })
            
        elif task == TaskType.SUMMARIZATION:
            params.update({
                "temperature": 0.3,  # Balanced for coherent but varied summaries
                "top_p": 0.9,
                "max_tokens": 1024,  # Typical summary length
            })
            
        elif task == TaskType.QUERY_ANSWERING:
            params.update({
                "temperature": 0.7,  # Higher for more diverse responses
                "top_p": 0.9,
                "max_tokens": 2048,  # Generous limit for complete answers
                "stream": True,      # Enable streaming for better UX
            })
            
        # Model-specific parameter adjustments
        if provider_lower == "openai":
            if "gpt-4" in model:
                # Higher token limit for GPT-4 models
                params["max_tokens"] = min(params.get("max_tokens", 2048), 4096)
                
        elif provider_lower == "anthropic":
            if "claude-3" in model:
                # Claude 3 specific settings
                params["max_tokens"] = min(params.get("max_tokens", 2048), 4096)
                
                # Use structured output if appropriate
                if task in [TaskType.ENTITY_EXTRACTION, TaskType.RELATION_EXTRACTION]:
                    params["system"] = "Respond only with properly formatted JSON."
                    
        return params
        
    def optimize_prompt(
        self,
        provider: str,
        task: TaskType,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """
        Optimize prompts for specific models and tasks.
        
        Args:
            provider: Provider name (e.g., 'openai', 'anthropic')
            task: Type of task to perform
            prompt: User prompt
            system_prompt: Optional system prompt
            
        Returns:
            Tuple of (optimized_prompt, optimized_system_prompt)
        """
        provider_lower = provider.lower()
        
        # Apply provider-specific optimizations
        if provider_lower == "anthropic":
            # Anthropic-specific prompt optimizations
            if task in [TaskType.ENTITY_EXTRACTION, TaskType.RELATION_EXTRACTION]:
                # Enhance system prompt for structured output
                if system_prompt:
                    system_prompt = f"{system_prompt}\n\nOutput should be valid JSON format."
                else:
                    system_prompt = "Output should be valid JSON format."
                    
        elif provider_lower == "openai":
            # OpenAI-specific prompt optimizations
            if task == TaskType.ENTITY_EXTRACTION and "gpt-3.5" in provider_lower:
                # Add specific instructions for GPT-3.5 to improve extraction quality
                prompt = f"{prompt}\n\nExtract all entities mentioned in the text. Be thorough and don't miss any entities."
                
        # Return optimized prompts
        return prompt, system_prompt


# Global instance for simplified access
_global_model_optimizer: Optional[ModelOptimizer] = None


def get_model_optimizer() -> ModelOptimizer:
    """Get the global model optimizer instance."""
    global _global_model_optimizer
    
    if _global_model_optimizer is None:
        _global_model_optimizer = ModelOptimizer()
        
    return _global_model_optimizer