"""Render scientific figures from a verified, existing dual-model app recording.

No inference, model download, simulator labels as predictions, or product behavior
change. Source RGB/masks/scores/tracks are immutable; evaluator truth is separately
marked. Requires the raw ignored acceptance directory and host dev dependencies.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import shutil
import textwrap
import zipfile

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Polygon
import numpy as np
from PIL import Image

from research_vision_eval import iou


BLUE = "#246A9E"
GREEN = "#287C60"
AMBER = "#B87914"
RED = "#AD3C40"
INK = "#24352D"
NAMES = {
    "moving": "Moving enrolled objects",
    "empty": "Empty background",
    "decoy": "Unregistered look-alike",
    "occluded": "Fully covered camera",
    "changed_view": "Changed view",
    "novel_angle": "Novel angle",
    "novel_lighting": "Novel lighting",
    "novel_distractors": "Novel distractors",
    "indistinguishable_front": "Identical visible faces",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matches(frame, expected):
    used, matched = set(), {}
    for det in sorted(
        frame["detections"], key=lambda d: d["model_score"], reverse=True
    ):
        options = [
            (iou(det["xyxy"], g["xyxy"]), j)
            for j, g in enumerate(expected)
            if j not in used and g["key"] == det["prompt_name"]
        ]
        overlap, index = max(options, default=(0.0, -1))
        if overlap >= 0.5:
            used.add(index)
            matched[det["detection_index"]] = index
    return matched, used


class Report:
    def __init__(self, directory, output, compact):
        self.base, self.out = directory.resolve(), output.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        raw = self.base / "app-runs.json"
        expected = json.loads(compact.read_text())["raw_file_sha256"]
        if digest(raw) != expected:
            raise RuntimeError(
                "Raw model-output digest differs from committed evidence; no substitute data."
            )
        self.runs = json.loads(raw.read_text())
        if digest(self.base / "quality.json") != digest(
            compact.parent / "quality.json"
        ):
            raise RuntimeError(
                "Metric digest differs from committed evaluator evidence."
            )
        self.quality = json.loads((self.base / "quality.json").read_text())
        self.truth = json.loads((self.base / "truth.json").read_text())
        self.capture = {
            r["frame_id"]: r
            for r in map(
                json.loads, (self.base / "capture-truth.jsonl").read_text().splitlines()
            )
        }
        self.refs = self.runs[0]["job"]["result"]["references"]
        self.policy = self.runs[0]["job"]["result"]["provenance"]["descriptor"][
            "decision_policy"
        ]
        if any(
            r["job"]["result"]["provenance"]["descriptor"]["decision_policy"]
            != self.policy
            for r in self.runs
        ):
            raise RuntimeError(
                "Paired figure requires the same recorded comparison policy."
            )
        self.known = {r["name"] for r in self.refs}
        self.input_hashes, self.figures = {}, []
        self.pdf = PdfPages(self.out / "figures.pdf")
        plt.rcParams.update(
            {
                "font.family": "DejaVu Sans",
                "font.size": 10,
                "axes.spines.top": False,
                "axes.spines.right": False,
                "text.color": INK,
                "axes.labelcolor": INK,
                "pdf.fonttype": 42,
                "svg.fonttype": "none",
            }
        )

    def image(self, sha):
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise RuntimeError("Invalid recorded image identifier.")
        path = self.base / "state/images" / f"{sha}.png"
        if digest(path) != sha:
            raise RuntimeError(f"Image integrity failure: {sha}")
        self.input_hashes[sha] = str(path.relative_to(self.base))
        with Image.open(path) as image:
            return np.asarray(image.convert("RGB"))

    def expected(self, frame, known_only=True):
        cap = self.capture[frame["frame_id"]]
        rows = self.truth["scenes"][cap["scene"]][cap["index"]]
        return [g for g in rows if not known_only or g["key"] in self.known]

    def title(self, fig, title, caption):
        fig.suptitle(title, x=0.035, y=0.985, ha="left", fontsize=17, fontweight="bold")
        fig.text(
            0.035, 0.018, textwrap.fill(caption, width=165), fontsize=9, va="bottom"
        )
        fig.tight_layout(rect=(0.02, 0.09, 0.99, 0.95), h_pad=2.0, w_pad=1.8)

    def save(self, fig, stem, title, caption, selections=None):
        self.title(fig, title, caption)
        for suffix in ("png", "svg"):
            fig.savefig(self.out / f"{stem}.{suffix}", dpi=180, facecolor="white")
            if suffix == "svg":
                path = self.out / f"{stem}.{suffix}"
                path.write_text(
                    "\n".join(line.rstrip() for line in path.read_text().splitlines())
                    + "\n"
                )
        self.pdf.savefig(fig, facecolor="white")
        self.figures.append(
            {
                "stem": stem,
                "title": title,
                "caption": caption,
                "selection": selections or [],
                "sha256": {
                    suffix: digest(self.out / f"{stem}.{suffix}")
                    for suffix in ("png", "svg")
                },
            }
        )
        plt.close(fig)

    def draw(self, ax, frame, overlays=False, focus=None, evaluator=None):
        ax.imshow(self.image(frame["image_sha"]))
        ax.set_xlim(0, frame["width"])
        ax.set_ylim(frame["height"], 0)
        ax.axis("off")
        if overlays:
            for det in frame["detections"]:
                supported = (
                    det["reference_comparison"]["decision"] == "supported_candidate"
                )
                color = GREEN if supported else AMBER
                polygon = det["mask_polygon_xy"]
                if len(polygon) >= 3:
                    ax.add_patch(
                        Polygon(polygon, facecolor=color, alpha=0.15, edgecolor="none")
                    )
                x1, y1, x2, y2 = det["xyxy"]
                ax.add_patch(
                    Rectangle(
                        (x1, y1),
                        x2 - x1,
                        y2 - y1,
                        fill=False,
                        edgecolor=color,
                        linewidth=1.3,
                        linestyle="-" if supported else "--",
                    )
                )
                track = next(
                    (
                        t
                        for t in frame["tracks"]
                        if t["detection_index"] == det["detection_index"]
                    ),
                    None,
                )
                label = f"p{det['detection_index'] + 1}" + (
                    f" / t{track['track_id']}" if track else ""
                )
                ax.text(
                    x1 + 2,
                    max(16, y1 - 4),
                    label,
                    color="white",
                    fontsize=7,
                    bbox={
                        "facecolor": color,
                        "alpha": 0.9,
                        "pad": 1,
                        "edgecolor": "none",
                    },
                )
        if focus is not None:
            x1, y1, x2, y2 = focus["xyxy"]
            ax.add_patch(
                Rectangle(
                    (x1, y1),
                    x2 - x1,
                    y2 - y1,
                    fill=False,
                    edgecolor=BLUE,
                    linewidth=2.0,
                )
            )
        if evaluator is not None:
            x1, y1, x2, y2 = evaluator["xyxy"]
            ax.add_patch(
                Rectangle(
                    (x1, y1),
                    x2 - x1,
                    y2 - y1,
                    fill=False,
                    edgecolor=RED,
                    linewidth=2,
                    linestyle="--",
                )
            )

    def references(self):
        fig, axes = plt.subplots(len(self.refs), 3, figsize=(14, 10))
        selections = []
        for row, ref in enumerate(self.refs):
            if len(ref["image_shas"]) != 3:
                raise RuntimeError(
                    "This figure layout requires the recorded three-reference experiment."
                )
            for column, sha in enumerate(ref["image_shas"]):
                ax = axes[row, column]
                ax.imshow(self.image(sha))
                ax.axis("off")
                ax.set_title(f"{ref['name']} / reference {column + 1}", fontsize=10)
                selections.append(
                    {
                        "object_id": ref["object_id"],
                        "reference_ordinal": column,
                        "image_sha": sha,
                    }
                )
        self.save(
            fig,
            "01-enrolled-references",
            "1  Registered visual reference inputs",
            "Authored synthetic reference crops, supplied through the real Library UI. Names identify enrollment inputs, not inferred identities. Reference ordinals do not invent measured camera poses. No model result is drawn on these inputs.",
            selections,
        )

    def scenes(self):
        selections = [
            {
                "scene": r["scene"],
                "frame_id": r["job"]["result"]["frames"][0]["frame_id"],
                "image_sha": r["job"]["result"]["frames"][0]["image_sha"],
            }
            for r in self.runs
        ]
        for overlay, stem, title in [
            (
                False,
                "02-nine-source-scenes",
                "2  Actual model-input images / all nine conditions",
            ),
            (
                True,
                "03-nine-model-outputs",
                "3  Recorded YOLOE masks, reference decisions and ByteTrack IDs",
            ),
        ]:
            fig, axes = plt.subplots(3, 3, figsize=(16, 13))
            for ax, run in zip(axes.flat, self.runs):
                frame = run["job"]["result"]["frames"][0]
                self.draw(ax, frame, overlay)
                count = sum(
                    d["reference_comparison"]["decision"] == "supported_candidate"
                    for d in frame["detections"]
                )
                ax.set_title(
                    NAMES[run["scene"]]
                    + (
                        f"\n{len(frame['detections'])} raw / {count} supported / {len(frame['tracks'])} tracks"
                        if overlay
                        else "\nfirst recorded frame of the job"
                    ),
                    fontsize=10,
                )
            caption = "Synthetic pinhole-renderer fixtures, not physical robot footage. Fixed selection: first recorded frame of each job, rather than best-performing frames. Full source-image hashes/frame IDs are in figure-manifest.json."
            if overlay:
                caption += " Green solid = custom reference rule passed; amber dashed = unresolved. p = raw proposal index, t = window-local track ID. These are recorded model/policy outputs, not confirmed identity or evaluator truth. All proposals, including errors, remain visible."
            self.save(fig, stem, title, caption, selections)
        for run in self.runs:
            frame = run["job"]["result"]["frames"][0]
            fig, ax = plt.subplots(figsize=(10, 8))
            self.draw(ax, frame, True)
            self.save(
                fig,
                f"scene-{run['scene']}",
                NAMES[run["scene"]] + " / recorded model output",
                "Synthetic input. Green = reference-supported candidate; amber = unresolved; p = proposal; t = local track ID. A rule pass is not verified identity. No evaluator boxes or labels alter predictions.",
                [
                    {
                        "scene": run["scene"],
                        "frame_id": frame["frame_id"],
                        "image_sha": frame["image_sha"],
                    }
                ],
            )

    def metrics(self):
        conditions = list(self.quality["scenes"])
        entries = self.quality["scenes"]
        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        y = np.arange(len(conditions))
        width = 0.36
        for offset, variant, color, label in [
            (-width / 2, "raw_yoloe", BLUE, "Raw YOLOE proposals"),
            (
                width / 2,
                "dinov2_reference_supported",
                GREEN,
                "Custom DINOv2 reference policy",
            ),
        ]:
            values = [
                entries[c]["variants"][variant]["false_positives"] for c in conditions
            ]
            bars = axes[0].barh(
                y + offset, values, height=width, color=color, label=label
            )
            axes[0].bar_label(bars, padding=3, fontsize=9)
        axes[0].set_yticks(y, [NAMES[c] for c in conditions])
        axes[0].invert_yaxis()
        axes[0].set_xlabel("False candidate observations (count)")
        maximum = max(
            e["variants"]["raw_yoloe"]["false_positives"] for e in entries.values()
        )
        axes[0].set_xlim(0, max(1, maximum) * 1.22)
        axes[0].legend(loc="lower right", fontsize=8)
        positive = [
            c
            for c in conditions
            if entries[c]["variants"]["raw_yoloe"]["ground_truth_enrolled_instances"]
        ]
        y = np.arange(len(positive))
        for offset, variant, color in [
            (-width / 2, "raw_yoloe", BLUE),
            (width / 2, "dinov2_reference_supported", GREEN),
        ]:
            rows = [entries[c]["variants"][variant] for c in positive]
            bars = axes[1].barh(
                y + offset, [100 * r["recall"] for r in rows], height=width, color=color
            )
            axes[1].bar_label(
                bars,
                labels=[
                    f"{r['true_positives']}/{r['ground_truth_enrolled_instances']}"
                    for r in rows
                ],
                padding=3,
                fontsize=9,
            )
        axes[1].set_yticks(y, [NAMES[c] for c in positive])
        axes[1].invert_yaxis()
        axes[1].set_xlim(0, 120)
        axes[1].set_xticks([0, 25, 50, 75, 100])
        axes[1].set_xlabel("Recall (%) / labels show counts")
        self.save(
            fig,
            "04-paired-errors-and-recall",
            "4  Paired false candidates and recall / retained failures",
            "Same recorded RGB inputs, references and YOLOE outputs for both variants. IoU >= 0.5 and enrolled class define evaluator matches. Recall is omitted where no enrolled objects occur: it is undefined there. Counts are correlated observations, not independent trials or real-room quality. "
            + f"Recorded custom thresholds: {self.policy['minimum_similarity']:.2f} similarity / {self.policy['minimum_margin']:.2f} margin.",
        )

    def attribution(self):
        entries = self.quality["scenes"]
        conditions = [
            c
            for c, e in entries.items()
            if e["variants"]["raw_yoloe"]["ground_truth_enrolled_instances"]
        ]
        kept, gate, missing = [], [], []
        for c in conditions:
            raw = entries[c]["variants"]["raw_yoloe"]
            selected = entries[c]["variants"]["dinov2_reference_supported"]
            kept.append(selected["true_positives"])
            gate.append(raw["true_positives"] - selected["true_positives"])
            missing.append(raw["false_negatives"])
        if min(gate) < 0:
            raise RuntimeError(
                "This simple attribution requires monotone matching counts."
            )
        fig, ax = plt.subplots(figsize=(13, 7))
        left = np.zeros(len(conditions))
        for values, color, label in [
            (kept, GREEN, "Retained true proposals"),
            (gate, AMBER, "True proposals rejected by custom gate"),
            (missing, RED, "Missing before the reference gate"),
        ]:
            bars = ax.barh(
                np.arange(len(conditions)), values, left=left, color=color, label=label
            )
            ax.bar_label(
                bars,
                labels=[str(v) if v else "" for v in values],
                label_type="center",
                color="white",
                fontsize=11,
            )
            left += values
        ax.set_yticks(np.arange(len(conditions)), [NAMES[c] for c in conditions])
        ax.invert_yaxis()
        ax.set_xlabel("Expected enrolled frame/object observations")
        ax.set_xlim(0, max(left) + 2)
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.12),
            ncol=1,
            frameon=False,
            fontsize=9,
        )
        self.save(
            fig,
            "05-stage-loss-attribution",
            "5  Where true observations are lost",
            "Derived from the recorded paired one-to-one evaluator counts, not new inference. Orange loss is caused by the project reference-decision stage; red loss occurs before that stage. This localizes losses but does not isolate the deeper cause of YOLOE misses (model, prompting, preprocessing or synthetic-domain fit).",
        )

    def failures(self):
        selected = []
        for scene, kind in [
            ("novel_angle", "true_rejection"),
            ("novel_lighting", "miss"),
            ("indistinguishable_front", "false_support"),
        ]:
            run = next(r for r in self.runs if r["scene"] == scene)
            found = None
            for frame in run["job"]["result"]["frames"]:
                expected = self.expected(frame)
                matched, used = matches(frame, expected)
                if kind == "miss":
                    missing = [g for i, g in enumerate(expected) if i not in used]
                    if missing:
                        found = (frame, None, missing[0])
                        break
                else:
                    for det in frame["detections"]:
                        support = (
                            det["reference_comparison"]["decision"]
                            == "supported_candidate"
                        )
                        qualifies = (
                            kind == "true_rejection"
                            and det["detection_index"] in matched
                            and not support
                        ) or (
                            kind == "false_support"
                            and det["detection_index"] not in matched
                            and support
                        )
                        if qualifies:
                            found = (frame, det, None)
                            break
                    if found:
                        break
            if found is None:
                raise RuntimeError(f"Recorded failure case missing: {scene}")
            selected.append((scene, kind, *found))
        fig, axes = plt.subplots(3, 4, figsize=(18, 12))
        selection = []
        titles = {
            "true_rejection": "True object rejected",
            "miss": "Object missed by YOLOE",
            "false_support": "Unknown alias passes custom rule",
        }
        for row, (scene, kind, frame, det, gt) in enumerate(selected):
            self.draw(axes[row, 0], frame, True, focus=det, evaluator=gt)
            axes[row, 0].set_title(titles[kind] + "\n" + NAMES[scene], fontsize=10)
            if det is not None:
                cmp = det["reference_comparison"]
                axes[row, 1].imshow(self.image(det["crop_image_sha"]))
                axes[row, 1].axis("off")
                axes[row, 1].set_title("Actual model-generated crop")
                axes[row, 2].imshow(self.image(cmp["best_reference_sha"]))
                axes[row, 2].axis("off")
                axes[row, 2].set_title("Closest recorded reference")
                classes = cmp["classes"]
                values = [c["score"] for c in classes]
                y = np.arange(len(classes))
                bars = axes[row, 3].barh(y, values, color=BLUE)
                axes[row, 3].bar_label(
                    bars, labels=[f"{v:.3f}" for v in values], padding=3, fontsize=8
                )
                axes[row, 3].set_yticks(y, [c["name"] for c in classes], fontsize=8)
                axes[row, 3].set_xlim(0, 1.08)
                axes[row, 3].axvline(
                    self.policy["minimum_similarity"],
                    color=AMBER,
                    linestyle="--",
                    label=f"Recorded custom threshold {self.policy['minimum_similarity']:.2f}",
                )
                axes[row, 3].set_xlabel(
                    "Max reference cosine / not probability", fontsize=8
                )
                axes[row, 3].set_title(
                    cmp["decision"]
                    + "\nmargin "
                    + (
                        f"{cmp['margin']:.3f}"
                        if cmp["margin"] is not None
                        else "unknown"
                    ),
                    fontsize=9,
                )
            else:
                axes[row, 1].axis("off")
                axes[row, 1].text(
                    0.5,
                    0.5,
                    "No matching model proposal\nNo substitute crop generated",
                    ha="center",
                    va="center",
                    transform=axes[row, 1].transAxes,
                )
                ref = next(r for r in self.refs if r["name"] == gt["key"])
                axes[row, 2].imshow(self.image(ref["image_shas"][0]))
                axes[row, 2].axis("off")
                axes[row, 2].set_title(
                    "Registered reference\n(evaluator selection)", fontsize=10
                )
                axes[row, 3].axis("off")
                axes[row, 3].text(
                    0.5,
                    0.5,
                    "Dashed red: evaluator-only GT.\nNo descriptor comparison\nfor this missed object.",
                    ha="center",
                    va="center",
                    transform=axes[row, 3].transAxes,
                )
            selection.append(
                {
                    "scene": scene,
                    "kind": kind,
                    "frame_id": frame["frame_id"],
                    "proposal_index": det["detection_index"] if det else None,
                    "evaluator_box": gt,
                }
            )
        self.save(
            fig,
            "06-failure-case-evidence",
            "6  Failure evidence / source frame, crop, reference and decision",
            "Fixed selection: first recorded failure satisfying each stated evaluator condition. Dashed red boxes are evaluation-only truth and were never model inputs; blue emphasis is the selected model proposal. No GT crop replaces a missing model crop. Identical-visible-face alias truth is distinct from the model-supported class. No predictions or thresholds were changed for this figure.",
            selection,
        )

    def tracking(self):
        fig, axes = plt.subplots(3, 1, figsize=(14, 10))
        names = [r["name"] for r in self.refs]
        colors = dict(zip(names, [BLUE, GREEN, RED]))
        for ax, scene in zip(
            axes, ["moving", "novel_angle", "indistinguishable_front"]
        ):
            run = next(r for r in self.runs if r["scene"] == scene)
            frames = run["job"]["result"]["frames"]
            refnames = {
                r["object_id"]: r["name"] for r in run["job"]["result"]["references"]
            }
            start = datetime.fromisoformat(frames[0]["captured_at"])
            points = defaultdict(list)
            for frame in frames:
                t = (
                    datetime.fromisoformat(frame["captured_at"]) - start
                ).total_seconds()
                for track in frame["tracks"]:
                    points[refnames[track["prompt_object_id"]]].append(
                        (t, track["track_id"])
                    )
            for name, rows in points.items():
                xy = np.asarray(rows)
                ax.scatter(xy[:, 0], xy[:, 1], s=34, color=colors[name], label=name)
            ids = sorted({int(p[1]) for rows in points.values() for p in rows})
            ax.set_yticks(ids)
            duration = (
                datetime.fromisoformat(frames[-1]["captured_at"]) - start
            ).total_seconds()
            ax.set_xlim(-0.05, max(0.1, duration) + 0.05)
            if ids:
                ax.set_ylim(min(ids) - 0.3, max(ids) + 0.75)
            else:
                supported = sum(
                    d["reference_comparison"]["decision"] == "supported_candidate"
                    for f in frames
                    for d in f["detections"]
                )
                ax.text(
                    0.5,
                    0.5,
                    f"No tracks returned\n{supported} reference-supported candidates across {len(frames)} frames",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
            ax.set_ylabel("Window-local track ID")
            ax.set_title(NAMES[scene], loc="left", fontsize=11)
            ax.set_xlabel(
                "Seconds since first captured frame / recorded ingestion clock"
            )
            if points:
                ax.legend(loc="upper right", fontsize=8, ncol=3)
            ax.grid(axis="x", alpha=0.15)
        self.save(
            fig,
            "07-recorded-track-timeline",
            "7  Recorded ByteTrack observations / gaps remain visible",
            "Each point is an actual returned track row; no interpolated motion or connecting line fills a gap. Colors identify enrolled prompt classes, not verified identities. IDs reset per window. The alias window returns no tracks despite reference-supported candidates; no track IDs are invented to fill that empty result. No predictive world-model claim is made.",
        )

    def complete_gallery(self):
        """Export every recorded frame locally; complete streams stay out of Git."""
        if self.truth.get("mode") != "synthetic" or any(
            r["job"]["mode"] != "synthetic" for r in self.runs
        ):
            raise RuntimeError(
                "Complete export requires the explicitly synthetic acceptance recording."
            )
        root = self.out / "complete"
        recording, visuals = root / "recording", root / "visuals"
        images = recording / "state/images"
        images.mkdir(parents=True)
        visuals.mkdir()
        for name in [
            "app-runs.json",
            "quality.json",
            "truth.json",
            "capture-truth.jsonl",
            "run-manifest.json",
            "artifact-failures.json",
        ]:
            shutil.copy2(self.base / name, recording / name)
        for path in (self.base / "state/images").glob("*.png"):
            if digest(path) != path.stem:
                raise RuntimeError(
                    "Stored image digest mismatch during complete export."
                )
            shutil.copy2(path, images / path.name)
        for scene, frames in self.truth["scenes"].items():
            for i in range(len(frames)):
                shutil.copy2(self.base / f"{scene}-{i}.png", recording)
        sections, entries = [], []
        for run in self.runs:
            scene = run["scene"]
            folder = visuals / "frames" / scene
            folder.mkdir(parents=True)
            cards = []
            for i, frame in enumerate(run["job"]["result"]["frames"]):
                cap = self.capture[frame["frame_id"]]
                if cap["scene"] != scene:
                    raise RuntimeError("Frame-to-scene evidence binding mismatch.")
                source = recording / f"{scene}-{cap['index']}.png"
                with Image.open(source) as original:
                    if not np.array_equal(
                        np.asarray(original.convert("RGB")),
                        self.image(frame["image_sha"]),
                    ):
                        raise RuntimeError(
                            "Captured pixels differ from the mapped rendered source."
                        )
                fig, ax = plt.subplots(figsize=(9, 7.5))
                self.draw(ax, frame, True)
                self.title(
                    fig,
                    NAMES[scene] + f" / recorded frame {i + 1}",
                    "Synthetic input and recorded model/policy outputs. Green = reference-supported; amber = unresolved. p = proposal; t = temporary track. No evaluator truth or invented motion is drawn. "
                    + frame["frame_id"],
                )
                path = folder / f"{i:03d}.png"
                fig.savefig(path, dpi=120, facecolor="white")
                plt.close(fig)
                relative = path.relative_to(visuals).as_posix()
                entry = {
                    "scene": scene,
                    "ordinal": i,
                    "frame_id": frame["frame_id"],
                    "captured_at": frame["captured_at"],
                    "captured_image_sha": frame["image_sha"],
                    "rendered_source": source.name,
                    "rendered_source_sha256": digest(source),
                    "overlay": relative,
                    "overlay_sha256": digest(path),
                }
                entries.append(entry)
                cards.append(
                    f'<figure><a href="{html.escape(relative)}"><img loading="lazy" src="{html.escape(relative)}" alt="Recorded model output"></a><figcaption>Frame {i + 1} / {html.escape(frame["captured_at"])}<br>{html.escape(frame["frame_id"])}<br><a href="../recording/state/images/{frame["image_sha"]}.png">Actual captured input PNG</a></figcaption></figure>'
                )
            sections.append(
                f'<section id="{html.escape(scene)}"><h2>{html.escape(NAMES[scene])}</h2><div class="grid">'
                + "".join(cards)
                + "</div></section>"
            )
        links = "".join(
            f'<li><a href="{f["stem"]}.png">{html.escape(f["title"])}</a> / <a href="{f["stem"]}.svg">SVG</a></li>'
            for f in self.figures
        )
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PuppyPi recorded vision evidence</title><style>body{font:15px/1.5 sans-serif;color:#24352d;margin:24px;max-width:1600px} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}figure{margin:0;border:1px solid #ddd;padding:12px}img{width:100%;height:auto}figcaption{overflow-wrap:anywhere;font-size:12px}a{color:#246a9e}</style><h1>Complete synthetic vision evidence</h1><p>__RECORDING_COUNTS__ These are authored renderer fixtures, not a physical robot run. Recorded outputs include errors; exact identity remains unverified. The gallery performs no inference.</p><p><a href="figures.pdf">Summary figure PDF</a> / <a href="../recording/app-runs.json">Full recorded model output</a> / <a href="full-frame-manifest.json">Every frame and hash</a></p><ul>'
            + links
            + "</ul>"
            + "".join(sections)
            + "</html>"
        )
        original_files = [
            self.base / f"{scene}-{i}.png"
            for scene, rows in self.truth["scenes"].items()
            for i in range(len(rows))
        ]
        summary = f"{len(original_files)} rendered source files, {len({digest(p) for p in original_files})} distinct file contents and {len(entries)} model-processed frames in this recording."
        page = page.replace("__RECORDING_COUNTS__", summary)
        (visuals / "index.html").write_text(page)
        (visuals / "full-frame-manifest.json").write_text(
            json.dumps(
                {
                    "scope": "complete_recorded_model_overlay_export_not_new_inference",
                    "frames": entries,
                },
                indent=2,
            )
            + "\n"
        )
        (root / "README.md").write_text(
            "# Complete synthetic vision evidence\n\nOpen visuals/index.html for every recorded frame. recording/ contains the original synthetic source images, content-addressed PNGs, immutable model outputs and evaluator-only truth. No model weights, database, credentials or camera/control service are included. Figures are derived from recorded predictions; no inference or task-quality claim is added.\n"
        )
        return root, visuals, len(entries)

    def finish(self):
        pages = self.pdf.get_pagecount()
        self.pdf.close()
        complete, visuals, frame_count = self.complete_gallery()
        sources = [
            self.base / f"{s}-{i}.png"
            for s in self.truth["scenes"]
            for i in range(len(self.truth["scenes"][s]))
        ]
        if not all(p.is_file() for p in sources):
            raise RuntimeError("A rendered source file is missing.")
        manifest = {
            "schema_version": 1,
            "artifact_type": "derived_scientific_figures_not_new_inference",
            "input_directory": str(self.base),
            "raw_output_sha256": digest(self.base / "app-runs.json"),
            "quality_sha256": digest(self.base / "quality.json"),
            "renderer_truth_sha256": digest(self.base / "truth.json"),
            "rendered_source_files": len(sources),
            "unique_rendered_file_contents": len({digest(p) for p in sources}),
            "model_processed_frames": sum(
                len(r["job"]["result"]["frames"]) for r in self.runs
            ),
            "source_images_used": self.input_hashes,
            "selection": "first recorded frame per scene; first qualifying failure per category",
            "prediction_policy": "raw recorded masks/boxes/scores/tracks retained; evaluator annotations explicitly separate",
            "figures": self.figures,
            "pdf_sha256": digest(self.out / "figures.pdf"),
            "pdf_pages": pages,
            "all_recorded_frame_overlays": frame_count,
            "renderer_source_sha256": digest(Path(__file__)),
        }
        (self.out / "figure-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        for path in self.out.iterdir():
            if (
                path.suffix in {".png", ".svg", ".pdf"}
                or path.name == "figure-manifest.json"
            ):
                shutil.copy2(path, visuals / path.name)
        archive = self.out / "complete-evidence.zip"
        with zipfile.ZipFile(
            archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as bundle:
            for path in sorted(complete.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(complete))
        (self.out / "archive-manifest.json").write_text(
            json.dumps(
                {
                    "archive": archive.name,
                    "sha256": digest(archive),
                    "bytes": archive.stat().st_size,
                    "complete_frame_overlays": frame_count,
                    "contents": "synthetic source PNGs, content-addressed images, raw outputs, evaluator-only truth, every-frame gallery and summary figures; no weights or credentials",
                },
                indent=2,
            )
            + "\n"
        )
        print(
            json.dumps(
                {
                    "rendered_sources": len(sources),
                    "unique_source_contents": manifest["unique_rendered_file_contents"],
                    "model_frames": manifest["model_processed_frames"],
                    "figures": len(self.figures),
                    "output": str(self.out),
                }
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--committed-compact", type=Path, required=True)
    args = parser.parse_args()
    report = Report(args.directory, args.output, args.committed_compact)
    try:
        report.references()
        report.scenes()
        report.metrics()
        report.attribution()
        report.failures()
        report.tracking()
        report.finish()
    finally:
        report.pdf.close()
        plt.close("all")


if __name__ == "__main__":
    main()
