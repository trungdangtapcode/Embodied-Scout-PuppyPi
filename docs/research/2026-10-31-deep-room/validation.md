# Deep research validation and artifact guide

Date: 2026-10-31. Canonical report:
[18 Deep research](../../18-deep-research-room-intelligence.md).
[HTML](report.html), [PDF](report.pdf) and [browser preview](report-preview.png)
are reading copies. The PDF has 19 pages; the figure and bibliography were
visually inspected alongside its first page.

## Evidence and source checks

- [sources.jsonl](sources.jsonl): 27 registered primary papers or official
  documentation records, with stable IDs, reading scope and source limitations.
- [evidence.jsonl](evidence.jsonl): 55 records; short exact quotations and bounded
  paraphrases have explicit types and locators. These are not full-paper copies.
- [claims.jsonl](claims.jsonl): 84 tracked records, including 79 scoped factual
  records and five synthesis/recommendation records. Manual qualifiers remain
  distinct from automated overlap scores.
- [source-metadata.json](source-metadata.json): additional primary metadata,
  preserving initially registered source records rather than changing identities.
- [repository-snapshots.json](repository-snapshots.json): 15 inspected source
  snapshots. Availability/terms inspection does not mean executable reproduction.
- [citation-map.json](citation-map.json) maps stable IDs to displayed numbers;
  [run_manifest.json](run_manifest.json) records workflow, assumptions and artifacts.

The retrieved skill's report validator passes structure, citation numbering,
bibliography completeness, placeholders, length, source count and its local
reference check. The strict claim-support check reports zero unsupported factual
records: 79 supported and five partial interpretation records. Its overlap scores
are heuristic; they do not prove entailment or calibration. Primary-section
inspection and independent critique supply the substantive review.

The citation checker successfully reached all 27 source URLs. It assigned 26
URL-verified statuses and one suspicious status because its title heuristic treats
the word `example` as placeholder text. That entry is the real aiortc server
example, source 22, whose official source was inspected. This is a manually
resolved false positive, retained here rather than hidden. No DOI verification
is claimed; URL accessibility alone does not verify a paper's experimental claims.

Independent reviewers identified and corrected unverified-hardware wording,
publication-versus-revision years, the need for byte-identical replay evidence,
and evidence-support labels distinct from hidden scene truth. Both members of
an indistinguishable retrospective pair warrant Unknown for the universal query,
even if a definite answer happens to match one hidden history.

## Rendering and repository validation

The HTML verifier passes after adding a semantic bibliography section. Chromium
loaded the report with no page errors, verified all images and 27 bibliography
entries, and found no horizontal overflow at 1280 px or 390 px. The editable SVG
was parsed and rendered to PNG, with text checked against canvas bounds and the
figure visually reviewed. The report preview is an actual document screenshot;
the research figure is a design illustration, not a delivered app screenshot.

PDF generation used Chromium. PDF text extraction confirmed the methodology and
complete bibliography; first, figure and final pages were rasterized and reviewed.
The skill's suggested renderer lacked inline-link handling, so reading copies
use an isolated CommonMark renderer and preserve clickable sources. Rendering
and PDF inspection tools ran in temporary tool environments without changing
project dependencies. No application/server process was started.

Repository validation uses `make check`. Code tests/builds, ROS, GPU inference,
real-phone behavior and physical robot trials are not repeated for these
documentation/assets changes. No model weights, complete recordings, secrets or
upstream implementation code are included. Proposed capability statuses remain
unchanged.
