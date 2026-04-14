from daily_paper.classification import TopicClassifier
from daily_paper.config import load_config


def test_vla_text_is_classified() -> None:
    config = load_config()
    classifier = TopicClassifier(config)
    result = classifier.classify(
        title="A Vision-Language-Action Policy for Long-Horizon Robot Manipulation",
        summary="We propose a robot policy with action tokens and hierarchical planning for tabletop manipulation.",
        query_groups=["VLA"],
    )
    assert result.include is True
    assert result.primary_topic == "VLA"
    assert "planning" in result.method_tags

