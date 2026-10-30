"""Perception package: candidate proposals, visual encoders, and few-shot memory."""

from teach_and_find.perception.encoder import (
    SpatialAppearanceEncoder,
    TorchHubBackboneEncoder,
    VisualEncoder,
    build_encoder,
)
from teach_and_find.perception.memory import (
    MatchResult,
    ObjectMemoryBank,
    ObjectRecord,
)
from teach_and_find.perception.proposals import CandidateProposal, CandidateProposalGenerator

__all__ = [
    "CandidateProposal",
    "CandidateProposalGenerator",
    "MatchResult",
    "ObjectMemoryBank",
    "ObjectRecord",
    "SpatialAppearanceEncoder",
    "TorchHubBackboneEncoder",
    "VisualEncoder",
    "build_encoder",
]
