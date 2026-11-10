import uuid

import pytest

from app.domain.identity import InvalidHandle, attendee_id_for, masked, normalize_handle


def test_email_and_username_are_normalized():
    assert normalize_handle("  Alex.N@Example.COM ") == ("alex.n@example.com", "email")
    assert normalize_handle("Kube_Fan-42") == ("kube_fan-42", "username")


@pytest.mark.parametrize(
    "bad", ["", "ab", "a b c", "-start", "x" * 40, "no@tld", "@x.io", "a@@b.io"]
)
def test_invalid_handles_are_rejected(bad):
    with pytest.raises(InvalidHandle):
        normalize_handle(bad)


def test_ids_are_stable_distinct_secret_bound_uuids():
    a1 = attendee_id_for("alex@example.com", b"s1")
    assert a1 == attendee_id_for("alex@example.com", b"s1")  # same handle, any device
    assert a1 != attendee_id_for("sam@example.com", b"s1")  # different people
    assert a1 != attendee_id_for("alex@example.com", b"s2")  # secret matters
    assert uuid.UUID(a1).version == 4  # passes the existing X-Guest-Id validation
    assert "alex" not in a1


def test_masking_hides_the_email():
    assert masked("alex@example.com", "email") == "al•••@example.com"
    assert masked("kube_fan", "username") == "kube_fan"
