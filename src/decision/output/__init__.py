"""Governed output registries, recommendation, policy, portfolio, and action instructions.

Execution-request handling now lives downstream in the `execution` package so
the output package continues to stop at action-instruction meaning.
"""

from .action_instruction_audit_adapter import ActionInstructionAuditAdapter
from .action_instruction_registry import (
    ActionInstructionClassDefinition,
    ActionInstructionRegistry,
    ActionInstructionRegistryError,
    ActionInstructionTemplateDefinition,
    JsonActionInstructionRegistry,
)
from .action_instruction_service import (
    ActionInstructionRecord,
    ActionInstructionRequest,
    ActionInstructionService,
)

from .portfolio_output_audit_adapter import PortfolioOutputAuditAdapter
from .portfolio_output_registry import (
    JsonPortfolioOutputRegistry,
    PortfolioOutputClassDefinition,
    PortfolioOutputRegistry,
    PortfolioOutputRegistryError,
    PortfolioOutputTemplateDefinition,
)
from .portfolio_output_service import (
    PortfolioOutputRecord,
    PortfolioOutputRequest,
    PortfolioOutputService,
)

from .policy_output_audit_adapter import PolicyOutputAuditAdapter
from .policy_output_registry import (
    JsonPolicyOutputRegistry,
    PolicyOutputClassDefinition,
    PolicyOutputRegistry,
    PolicyOutputRegistryError,
    PolicyOutputTemplateDefinition,
)
from .policy_output_service import (
    PolicyOutputRecord,
    PolicyOutputRequest,
    PolicyOutputService,
)

from .recommendation_audit_adapter import RecommendationAuditAdapter
from .recommendation_registry import (
    JsonRecommendationRegistry,
    RecommendationClassDefinition,
    RecommendationRegistry,
    RecommendationRegistryError,
    RecommendationTemplateDefinition,
)
from .recommendation_service import (
    RecommendationRecord,
    RecommendationRequest,
    RecommendationService,
)

__all__ = [
    "ActionInstructionAuditAdapter",
    "ActionInstructionClassDefinition",
    "ActionInstructionRecord",
    "ActionInstructionRegistry",
    "ActionInstructionRegistryError",
    "ActionInstructionRequest",
    "ActionInstructionService",
    "ActionInstructionTemplateDefinition",
    "JsonActionInstructionRegistry",
    "JsonPortfolioOutputRegistry",
    "JsonPolicyOutputRegistry",
    "JsonRecommendationRegistry",
    "PortfolioOutputAuditAdapter",
    "PortfolioOutputClassDefinition",
    "PortfolioOutputRecord",
    "PortfolioOutputRegistry",
    "PortfolioOutputRegistryError",
    "PortfolioOutputRequest",
    "PortfolioOutputService",
    "PortfolioOutputTemplateDefinition",
    "PolicyOutputAuditAdapter",
    "PolicyOutputClassDefinition",
    "PolicyOutputRecord",
    "PolicyOutputRegistry",
    "PolicyOutputRegistryError",
    "PolicyOutputRequest",
    "PolicyOutputService",
    "PolicyOutputTemplateDefinition",
    "RecommendationAuditAdapter",
    "RecommendationClassDefinition",
    "RecommendationRecord",
    "RecommendationRegistry",
    "RecommendationRegistryError",
    "RecommendationRequest",
    "RecommendationService",
    "RecommendationTemplateDefinition",
]