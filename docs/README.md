# PuppyPi documentation

Read current status and plans before using historical prototype claims in a
demonstration or report.

**Read first: [FATAL / CRITICAL / LETHAL capability-integrity review — OPEN / FAIL](review/2026-10-31-fatal-critical-lethal-capability-integrity.md).**
This is a mandatory correction to prior capability reporting. It audits actual
code, simulator shortcuts, missing AI/research integration and the no-fallback
acceptance rule. Documentation completion does not close the incident.

For a visual app tour, start with the
[eight-screenshot walkthrough](14-mobile-console-gallery.md), then the
[placement, evidence and control figures](13-mobile-console.md). Screenshots are
versioned in this repository and show the synthetic application, not hardware
validation.

For a first read, open [12 Deployment map](12-deployment-map.md): an annotated
SVG/PNG overview, environment nesting, file-to-machine table, data-flow sequence,
and the current limits of the robot/phone adapters. It explains host versus Pi,
Python versus native code, and venv versus Docker/ROS before the research plans.

## Current project direction

| Document | Purpose |
| --- | --- |
| [00 Project status](00-project-status.md) | Implemented behavior, evidence boundaries, hardware assumptions |
| [06 Feature roadmap](06-feature-roadmap.md) | 40 feature entries with status, dependencies, priorities, and demo criteria |
| [07 Research program](07-research-program.md) | Five tracks, hypotheses, related work, baselines, evaluation |
| [08 Shared architecture](08-system-evolution.md) | Reuse register, boundaries, proposed records and integration order |
| [09 Demo acceptance](09-demo-acceptance.md) | Scenarios and proposed experiment/evidence manifests |
| [10 Operator workflows](10-operator-workflows.md) | Implemented persistent library, history, annotation-driven inspection and report export |
| [11 Phone Observer research](11-phone-observer-research.md) | Fixed-phone external view, verified sources/code, ego/exo baselines and adjustable 16-week schedule |
| [12 Deployment map](12-deployment-map.md) | Visual host/Pi/firmware placement, Python/native runtimes, Docker/ROS boundaries and actual protocol |
| [13 Mobile field console](13-mobile-console.md) | Preact PWA, FastAPI host, Pi relay, run commands, operator workflows and control/evidence limits |
| [14 Screenshot walkthrough](14-mobile-console-gallery.md) | Eight actual phone/desktop captures, annotated operator flows and capture provenance |
| [15 Next-feature research](15-next-feature-research.md) | Verified reuse candidates, six prioritized extensions, one main research hypothesis and a 16-week sequence |
| [16 Room Patrol proposal](16-room-patrol-world-model-proposal.md) | Five-layer room model, bounded patrol, verified scene-graph/mapping work, sensor choices and paired evaluation |
| [17 Deep room-inspection research](17-deep-research-active-room-inspection.md) | Twelve-work prior-art audit, source-release checks, joint change/source-diagnosis proposal, visual experiment and strong baselines |
| [18 Skill-based deep research](18-deep-research-room-intelligence.md) | 27-source evidence-tracked review, temporal observability, counterfactual-history benchmark and acquisition proposal; [HTML](research/2026-10-31-deep-room/report.html), [19-page PDF](research/2026-10-31-deep-room/report.pdf), [validation](research/2026-10-31-deep-room/validation.md) |
| [19 Application delivery](19-application-delivery-plan.md) | Implemented Room memory, evidence queries and visual review; application-first monitoring, perception, phone and patrol sequence |
| [20 Executed upstream validation](20-room-memory-upstream-validation.md) | Mind Palace + GPT-4o/GPT-6 Luna component replays, actual outputs/reproducer, failed reference benchmark and ReMEmbR profile; no app integration claim |
| [21 Mind Palace fix proposal](21-mind-palace-integration-fix-proposal.md) | Source-backed contract defects, reproduced offline probes, tested Huey worker mechanism and accepted historical design; implementation/evidence in document 22 |
| [22 Recorded-memory app](22-mind-palace-app.md) | Actual pinned Mind Palace worker/API/UI integration, scoped synthetic model evidence and remaining gates |
| [23 Mobile runtime proposal](23-mobile-runtime-decision.md) | PWA/Capacitor/native tradeoffs; APK remains unimplemented |
| [24 Executed visual inspection](24-yoloe-vision.md) | Actual YOLOE/DINOv2/ByteTrack recorded-window profile, provenance and unresolved identity quality |
| [25 Visual identity proposal](25-visual-identity-fix-proposal.md) | Historical accepted dual-model revision and scoped execution evidence |
| [26 Interactive target tracking](26-interactive-target-tracking.md) | Proposed point/box → SAM 2.1 → Cutie live sessions; ten-repository audit, application contracts, failure/recovery gates and [design figures](research/2026-11-02-interactive-tracking/design-figures.pdf); not implemented |
| [Current code-integrity audit](review/2026-11-01-code-integrity-audit.md) | Silent substitutes, scripted labels, custom-method disclosures, source-call probe and explicit unresolved gaps |
| [Contributor guide](../CONTRIBUTING.md) | Setup, checks, commit conventions, review and evidence workflow |
| [Agent instructions](../AGENTS.md) | Repository-specific instructions for coding agents |
| [2026-10-31 handoff](handoffs/2026-10-31-handoff.md) | Repository bootstrap, verification, and next implementation steps |

## Historical baseline

Documents 01–05 and the original handoff are preserved source material. Their
claims must be read alongside [current evidence status](00-project-status.md).

| Document | Original subject |
| --- | --- |
| [01 Open-source stack](01-sota-and-open-source-stack.md) | Candidate papers and repositories |
| [02 Driver audit](02-deployment-and-hiwonder-driver-audit.md) | Vendor driver findings and deployment assumptions |
| [03 Algorithms and ablation](03-algorithms-and-ablation-plan.md) | Initial memory, planning, verifier and FSM formulations |
| [04 Experimental results](04-experimental-results.md) | Historical synthetic benchmark and visualizations |
| [05 Hardware guide](05-hardware-ros2-sim2real-guide.md) | Proposed robot/host boundary and ROS 2 integration |
| [2026-10-30 handoff](handoffs/2026-10-30-handoff.md) | Original session snapshot and continuation steps |

Use `docs/handoffs/YYYY-MM-DD-handoff.md` for new handoffs. Record actual tests,
remaining work, assumptions, and the next concrete implementation step.
