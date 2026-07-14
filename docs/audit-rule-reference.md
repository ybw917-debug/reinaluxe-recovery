# Article Audit Rule Reference

Rule set `1.0` uses immutable thresholds. These are audit heuristics, not
search-engine requirements:

- meta description: short below 70 characters; long above 160;
- paragraph: very short at 5 words or fewer; very long at 200 or more;
- derived body: unusually low below 300 words; unusually high above 5,000;
- external links: excessive candidate above 25.

Title/heading checks cover missing title/H1, multiple H1, empty headings, level
jumps, repeats, and title/H1 differences after lowercase alphanumeric
normalization. Metadata checks cover description and canonical presence/URL
normalization. Date ordering remains enforced by the source Article contract.

Body checks cover usable content, paragraph lengths, derived word count, and
identical normalized within-page blocks. CTA candidates require identical
blocks containing click, buy, shop, subscribe, contact, or learn more.
Conclusion candidates require identical blocks beginning with in conclusion,
to conclude, in summary, or to summarize.

Image, link, FAQ, and schema checks use only normalized fields. Locally absent
internal targets are candidates; external links are not fetched. FAQ schema
without visible FAQ content is a candidate. Strict Article validation makes
some malformed-state rules relevant only to legacy or constructed inputs.

Every finding cites a field or derived count. False positives can occur for
intentionally short content, canonical redirects, unimported pages, and repeated
editorial phrasing. No causal claim, score, similarity, embedding, or LLM is used.
