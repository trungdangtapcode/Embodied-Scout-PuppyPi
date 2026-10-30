# PuppyPi Teach & Find — Technical Documentation

 Technical research, open-source reference stack, hardware driver audit, and deployment guide for **PuppyPi Standard** (*Active Object Search Using Few-Shot Visual Memory and Topological Navigation*).

## Document Map

| Document | Focus |
| :--- | :--- |
| [01 — Open-Source Stack & SOTA](01-sota-and-open-source-stack.md) | Curated GitHub repositories and papers to build upon (`YOLOE`, `DINOv2`, `CNOS`, `IEVE`, `RoboHop`, `ViNT`) and thesis novelty boundaries. |
| [02 — Deployment & Hiwonder Driver Audit](02-deployment-and-hiwonder-driver-audit.md) | Why `.venv` on the GPU PC + lightweight Edge Bridge on PuppyPi beats distributed ROS 2 Docker over Wi-Fi, plus critical bugs/limits found in Hiwonder's `ros2` source code. |
| [03 — Algorithms & Ablation Plan](03-algorithms-and-ablation-plan.md) | Mathematical formulation of the 4 core modules mapped to `teach_and_find/` and the 30-trial ablation benchmark design. |
| [04 — Experimental Results](04-experimental-results.md) | Closed-loop 3D visual demo dashboard, 40-trial 4-way ablation table, and 3D MuJoCo CAD renders (`outputs/`). |
| [05 — Hardware, ROS 2 & Sim-to-Real Guide](05-hardware-ros2-sim2real-guide.md) | Visual Mermaid diagrams of PuppyPi's two physical boards (Raspberry Pi + STM32), onboard ROS 2 nodes, and portable Sim-to-Real deployment modes. |
| [Handoff — 2026-10-30](handoffs/2026-10-30-handoff.md) | Dated session handoff (`2026-10-30` VN / `2026-10-31` JST): status snapshot, file map, verified commands, metrics, and next-session roadmap. |

## Quick Start (Host GPU Workstation)

```bash
source /home/nguyentnt/PDWAIA/ecus/hi/.venv/bin/activate
pytest
```
