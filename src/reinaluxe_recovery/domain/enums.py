"""Controlled vocabularies used by the Content Audit domain."""

from enum import StrEnum


class ArticleStatus(StrEnum):
    """Lifecycle state observed for an article."""

    UNKNOWN = "unknown"
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REMOVED = "removed"


class ContentType(StrEnum):
    """Editorial role of a normalized article."""

    INFORMATIONAL_ARTICLE = "informational_article"
    BUYING_GUIDE = "buying_guide"
    BRAND_REVIEW = "brand_review"
    AUTHENTICATION_GUIDE = "authentication_guide"
    CRAFTSMANSHIP_GUIDE = "craftsmanship_guide"
    COMPARISON = "comparison"
    HUB = "hub"
    OTHER = "other"


class SearchIntent(StrEnum):
    """Human search goal associated with an article or topic."""

    INFORMATIONAL = "informational"
    COMMERCIAL_INVESTIGATION = "commercial_investigation"
    TRANSACTIONAL = "transactional"
    NAVIGATIONAL = "navigational"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class EvidenceSourceType(StrEnum):
    """Permitted source categories for factual evidence."""

    CRAWL_SNAPSHOT = "crawl_snapshot"
    FIRST_PARTY_CONTENT = "first_party_content"
    SEARCH_CONSOLE = "search_console"
    ANALYTICS = "analytics"
    OWNER_DOCUMENT = "owner_document"
    EXTERNAL_REFERENCE = "external_reference"
    MANUAL_OBSERVATION = "manual_observation"


class EvidenceConfidence(StrEnum):
    """Confidence assigned to a factual evidence reference."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class ReviewDecision(StrEnum):
    """Owner or reviewer disposition of a recommendation."""

    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    DEFERRED = "deferred"


class RiskLevel(StrEnum):
    """Qualitative severity without an embedded scoring formula."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryAction(StrEnum):
    """Controlled editorial actions proposed for an article."""

    KEEP = "keep"
    REWRITE = "rewrite"
    MERGE = "merge"
    ARCHIVE = "archive"
    CONVERT_TO_HUB = "convert_to_hub"
    MANUAL_REVIEW = "manual_review"


class LinkType(StrEnum):
    """Relationship of a link to the source article."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    AFFILIATE = "affiliate"
    UNKNOWN = "unknown"


class SchemaType(StrEnum):
    """Supported structured-data categories."""

    ARTICLE = "article"
    FAQ_PAGE = "faq_page"
    BREADCRUMB_LIST = "breadcrumb_list"
    PRODUCT = "product"
    ORGANIZATION = "organization"
    WEBSITE = "website"
    OTHER = "other"


class ClaimVerificationStatus(StrEnum):
    """Verification state of a community claim."""

    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"


class MetricScope(StrEnum):
    """Scope of a performance snapshot."""

    PAGE = "page"
    SITE = "site"


class SimilarityScope(StrEnum):
    """Content area described by a similarity finding."""

    INTRODUCTION = "introduction"
    SECTION = "section"
    FAQ = "faq"
    CONCLUSION = "conclusion"
    CALL_TO_ACTION = "call_to_action"
    FULL_CONTENT = "full_content"
    SEARCH_INTENT = "search_intent"


class RiskCategory(StrEnum):
    """Observed concern represented by a risk assessment."""

    STRUCTURAL_REPETITION = "structural_repetition"
    SEARCH_INTENT_OVERLAP = "search_intent_overlap"
    CONTENT_QUALITY = "content_quality"
    EVIDENCE_GAP = "evidence_gap"
    OUTDATED_CONTENT = "outdated_content"
    TECHNICAL = "technical"
    OTHER = "other"
