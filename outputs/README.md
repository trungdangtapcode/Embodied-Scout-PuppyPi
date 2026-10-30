# Synthetic baseline evidence

The tracked JSON, PNG, GIF, and AprilTag files are the synthetic artifacts
inherited from the 2026-10-30 session. Their reported results are described in
[the experimental record](../docs/04-experimental-results.md).

- `ablation_summary.json` and `ablation_benchmark.png`: 40 trials per variant,
  four variants, using the handcrafted spatial appearance encoder.
- `demo_mission_dashboard.png` and `camera_frames/`: rendered camera crops and
  search/verification decisions in the synthetic box scenario.
- `puppypi_3d_overview.png` and `puppypi_3d_mission.gif`: MuJoCo CAD visualization
  and scripted replay, not a physical closed-loop controller evaluation.
- `mission_replay.gif` and `mission_replay_preview.png`: synthetic mission replay.
- `apriltags_36h11/`: generated station markers. Measure the printed marker's
  black square against the configured physical tag size; page margins and the
  white border are not part of that size.

The original run's dependency lock and Git revision were not captured. The new
`uv.lock` describes the repository bootstrap environment, not retrospective
provenance for these historical results. A rerun should record its own revision,
configuration, seeds, environment, and output hashes.

Use ignored `runs/<run-id>/` for new experiments and private robot recordings.
Promote only reviewed, relevant evidence to this directory with an accompanying
manifest. Never label a rendered replay as a real robot trial.
