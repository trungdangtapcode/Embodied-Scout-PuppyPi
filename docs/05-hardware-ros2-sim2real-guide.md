# 05. PuppyPi Hardware Stack, ROS 2 Role & Portable Sim-to-Real Guide

This guide visually explains **what runs inside the physical PuppyPi Standard boards**, **what role ROS 2 plays**, **where the MuJoCo 3D simulator sits**, and **how `teach_and_find` ports to the real robot with minimal friction**.

---

## 1. Inside the Physical PuppyPi Standard (Two Boards + Full Onboard ROS 2)

A physical Hiwonder PuppyPi Standard carries **two stacked circuit boards**. The upper **Raspberry Pi** runs the **entire Linux + ROS 2 Humble environment (multiple ROS 2 nodes simultaneously)**, while the lower **STM32 expansion board** handles real-time servo PWM and battery power:

```mermaid
flowchart TB
    subgraph HardwareTop["UPPER BOARD: Raspberry Pi 4B / 5 (Linux SBC)"]
        OS["Raspberry Pi OS (Linux Host)"]
        subgraph DockerROS["Hiwonder Preinstalled Docker Container (Ubuntu 22.04 + ROS 2 Humble)"]
            N1["Node 1: usb_cam (Publishes 640x480 /image_raw)"]
            N2["Node 2: puppy_control / puppy.py (Quadruped Inverse Kinematics)"]
            N3["Node 3: ros_robot_controller (Serial Bridge to STM32)"]
            N4["Node 4: Your Slot! (~60-line Wi-Fi Relay OR TeachAndFindRos2Node)"]

            N1 -- "/image_raw" --> N4
            N4 -- "/puppy_control/velocity_move & /pose" --> N2
            N2 -- "8 joint angle targets" --> N3
        end
        OS --> DockerROS
    end

    CAM["Head Wide-Angle RGB Camera"] -- "USB Cable" --> N1

    subgraph HardwareBottom["LOWER BOARD: ROS Robot Controller (STM32 MCU)"]
        MCU["STM32 Real-Time Microcontroller (No Linux / No ROS)"]
        IMU["MPU6050 6-Axis IMU"]
        PWR["7.4V LiPo Power Distribution"]
        IMU --> MCU
        PWR --> MCU
    end

    N3 <== "UART / GPIO Serial (Servo targets & IMU stream)" ==> MCU

    S1["8 Bus Servos (LF, RF, LB, RB x 2 DOF)"]
    MCU == "High-Current Servo Bus / PWM" ==> S1
```

Key takeaway: **Nodes 1, 2, and 3 are already preinstalled and auto-started by Hiwonder on boot.** You never rewrite camera drivers, inverse kinematics, or STM32 serial packets — your software simply plugs in as **Node 4**.

---

## 2. Clean Sim-to-Real Boundary ("Zero-ROS Core")

All intelligence in `teach_and_find/` is written in **pure Python (`numpy` + `opencv`) with zero hard dependency on `rclpy` or `mujoco`**. The boundary between the brain and the body consists of **one input (`frame_bgr`)** and **one output (`PuppyActionCommand`)**:

```mermaid
flowchart LR
    subgraph Brain["CORE BRAIN: teach_and_find/ (Pure Python, Zero ROS Dependency)"]
        TAG["AprilTag PnP (apriltag_pose.py)"]
        MEM["Few-Shot Object Memory (memory.py)"]
        PLN["Active Search Planner (planner.py)"]
        VER["Multi-View Verifier (verification.py)"]
        FSM["Mission Controller FSM (mission.py)"]

        TAG --> FSM
        MEM --> VER
        PLN --> FSM
        VER --> FSM
    end

    subgraph SimWorld["MODE 1: Host .venv Simulation (No ROS / No Docker)"]
        MJ["3D MuJoCo CAD Arena + EGL GPU (mujoco_arena.py)"]
        PH["Fast 3D Pinhole Benchmark Sim (world3d.py)"]
    end

    subgraph RealWorld["MODE 2: Physical PuppyPi Robot"]
        BRG["ROS 2 Payload Translator (ros2_bridge.py)"]
        PI["PuppyPi Raspberry Pi (ROS 2 Humble)"]
        BRG --> PI
    end

    MJ -- "Rendered head_rgb (640x480)" --> Brain
    PH -- "Rendered RGB (640x480)" --> Brain
    Brain -- "PuppyActionCommand (vx, vy, yaw_rate, pitch)" --> MJ

    PI -. "Live /image_raw (640x480)" .-> Brain
    Brain -. "translate_action_to_ros_payload()" .-> BRG
```

---

## 3. Two Portable Deployment Modes on Real Hardware

```mermaid
flowchart TB
    subgraph ModeA["OPTION A: Offboard Wi-Fi Brain (Recommended for Dev & Heavy DINOv2)"]
        direction LR
        PC_A["Your Laptop / GPU Server (.venv) Runs full teach_and_find + GPU Backbone"]
        PI_A["PuppyPi Raspberry Pi (Vendor ROS 2 Container) Runs 1 tiny ~60-line socket relay + 0.3s Watchdog"]
        PC_A -- "JSON command (vx, vy, yaw_rate, pitch)" --> PI_A
        PI_A -- "Compressed JPEG (~25 KB/frame over Wi-Fi)" --> PC_A
    end

    subgraph ModeB["OPTION B: 100% Onboard Brain (Standalone, No Laptop / Wi-Fi Required)"]
        direction LR
        PI_B["PuppyPi Raspberry Pi (Vendor ROS 2 Container) Copy teach_and_find/ (~35 KB) & run TeachAndFindRos2Node"]
        ROS_B["Vendor Nodes (/image_raw & /puppy_control/*)"]
        ROS_B -- "Local ROS 2 topic" --> PI_B
        PI_B -- "Direct rclpy publish" --> ROS_B
    end
```

| Criterion | Option A — Offboard `.venv` + Thin Relay on Pi | Option B — 100% Onboard inside Pi ROS 2 Container |
| :--- | :--- | :--- |
| **Files copied to PuppyPi** | **1 script (~60 LoC)** | `teach_and_find/` package (~35 KB) |
| **Extra `pip` packages on Pi** | **Zero** (uses vendor `rclpy`, `cv2`, `socket`) | **Zero** for spatial encoder; `onnxruntime` for quantized DINOv2 |
| **Compute budget** | Full laptop/workstation GPU | Raspberry Pi 4B / 5 CPU |
| **Wi-Fi disconnect safety** | Onboard `0.3 s` watchdog stops all servos immediately | Independent of Wi-Fi |

---

## 4. End-to-End 150 ms Control Tick Sequence

```mermaid
sequenceDiagram
    participant Cam as Nose USB Camera
    participant RosPi as Onboard ROS 2 (usb_cam + puppy_control)
    participant Brain as teach_and_find Brain (FSM + Verifier)
    participant STM as Lower STM32 Board (8 Servos)

    Cam->>RosPi: 640x480 BGR frame
    RosPi->>Brain: Deliver frame (/image_raw or JPEG over Wi-Fi)
    Brain->>Brain: 1. AprilTag IPPE_SQUARE pose estimation
    Brain->>Brain: 2. Crop foreground proposal + query ObjectMemoryBank
    Brain->>Brain: 3. Frontal 0 deg sim=0.98 (ambiguous!) -> command lateral verification arc
    Brain->>RosPi: translate_action_to_ros_payload(vy != 0 -> /puppy_control/velocity_move)
    Note over Brain,RosPi: Automatically routes y != 0 to /velocity_move and clamps Pose.yaw = 0
    RosPi->>RosPi: puppy.py solves 4-leg IK into 8 servo angles
    RosPi->>STM: Send UART serial frame
    STM->>STM: Drive 8 leg servos along side-view arc
```
