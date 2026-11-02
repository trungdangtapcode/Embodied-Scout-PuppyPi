def test_revised_gallery_readout_preserves_raw_prompt_without_using_it_as_identity():
    from dataclasses import replace
    from teach_and_find.config import VisionSettings
    from teach_and_find.dinov2_adapter import compare_reference_scores

    references = [
        {"object_id": "target", "name": "target", "image_shas": ["a"]},
        {"object_id": "decoy", "name": "decoy", "image_shas": ["b"]},
    ]
    original = VisionSettings()
    revised = replace(original, profile_version=3)
    old = compare_reference_scores(
        [[0.89038], [0.70502]], references, "decoy", original
    )
    new = compare_reference_scores([[0.89038], [0.70502]], references, "decoy", revised)
    assert old["decision"] == "unresolved"
    assert old["reason"] == "detector_descriptor_disagreement"
    assert (
        new["decision"] == "supported_candidate" and new["best_object_id"] == "target"
    )
    assert new["prompt_score"] == 0.70502
    # Agreement removal must not remove similarity or ambiguity rejection.
    assert (
        compare_reference_scores([[0.79], [0.60]], references, "target", revised)[
            "decision"
        ]
        == "unresolved"
    )
    assert (
        compare_reference_scores([[0.89], [0.88]], references, "target", revised)[
            "decision"
        ]
        == "unresolved"
    )
