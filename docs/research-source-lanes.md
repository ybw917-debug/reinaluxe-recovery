# Research source lanes

Each request configures priorities plus query and accepted-source quotas for six lanes:

- `community_reddit`: public Reddit experience, disagreement, and moderation context;
- `community_forums`: public specialist forums and communities;
- `primary_official`: primary specifications, definitions, policy, and official records;
- `expert_editorial`: attributed expert methods and critical context;
- `commercial_observation`: prices, listings, and seller claims treated only as scoped observations;
- `visual_image`: source-linked image discovery and metadata.

Deterministic screening normalizes HTTP(S) URLs, removes common tracking parameters, rejects missing/invalid URLs, applies domain/path policies, parses dates, classifies strong Reddit/forum/official signals, enforces quotas, preserves the originating query, and removes exact duplicates. Only then may GLM analysis assess relevance, first-hand versus hearsay, specificity, promotion risk, access quality, atomic claims, limitations, topic mapping, and article-section mapping.

The AAA template gives Reddit the highest priority but also allocates every other lane. The planner itself contains no AAA family or brand rule. Reddit-specific syntax appears only when a request enables the generic `community_reddit` lane.
