# PuppyPi Teach & Find

**Active Object Search Using Few-Shot Visual Memory and Topological Navigation** for **Hiwonder PuppyPi Standard**.

## Documentation (`docs/`)

- [**docs/README.md**](docs/README.md) — Documentation index
- [**docs/01-sota-and-open-source-stack.md**](docs/01-sota-and-open-source-stack.md) — Open-source repos & papers to build upon (`YOLOE`, `DINOv2`, `CNOS`, `IEVE`, `RoboHop`, `ViNT`) and thesis novelty boundaries
- [**docs/02-deployment-and-hiwonder-driver-audit.md**](docs/02-deployment-and-hiwonder-driver-audit.md) — Why `.venv` on GPU host + lightweight Edge Bridge on PuppyPi beats distributed ROS 2 Docker, plus 4 critical bugs/limits found in Hiwonder's `ros2` driver source
- [**docs/03-algorithms-and-ablation-plan.md**](docs/03-algorithms-and-ablation-plan.md) — Core mathematical formulations, state machine diagram, and 30-trial ablation study matrix
- [**docs/04-experimental-results.md**](docs/04-experimental-results.md) — Actual experimental numbers, visual plots & 3D MuJoCo PuppyPi CAD renders (`100%` success vs `25%` baseline, `-31.9%` stations checked)
- [**docs/05-hardware-ros2-sim2real-guide.md**](docs/05-hardware-ros2-sim2real-guide.md) — Visual Mermaid architecture of PuppyPi's physical boards (Pi + STM32), ROS 2 nodes, and Sim-to-Real bridge
- [**docs/handoffs/2026-10-30-handoff.md**](docs/handoffs/2026-10-30-handoff.md) — Dated session handoff (`2026-10-30` VN / `2026-10-31` JST): file map, verified commands, and next steps

## Quick Start

```bash
source /home/nguyentnt/PDWAIA/ecus/hi/.venv/bin/activate
pytest
```
