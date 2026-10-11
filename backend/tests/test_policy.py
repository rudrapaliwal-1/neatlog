from backend.policy import patch_hash, validate_patch
from .conftest import PATCH


def test_exact_utf8_hash_and_valid_diff(setup):
    _, _, _, settings = setup
    assert patch_hash("é") != patch_hash("e")
    assert patch_hash(PATCH) != patch_hash(PATCH + "\n")
    assert validate_patch("bola-demo-v1", PATCH, ["app/access.py"], 0, settings).allowed


def test_patch_policy_rejections(setup):
    _, _, _, settings = setup
    cases = [
        ("wrong-target", PATCH, ["app/access.py"], 0),
        ("bola-demo-v1", PATCH, ["other.py"], 0),
        ("bola-demo-v1", PATCH, ["app/access.py"], 3),
        ("bola-demo-v1", PATCH.replace("app/access.py", "../app/access.py"), ["../app/access.py"], 0),
        ("bola-demo-v1", PATCH.replace("app/access.py", "/app/access.py"), ["/app/access.py"], 0),
        ("bola-demo-v1", PATCH.replace("app/access.py", "tests/test_access.py"), ["tests/test_access.py"], 0),
        ("bola-demo-v1", PATCH + "GIT binary patch\n", ["app/access.py"], 0),
        ("bola-demo-v1", PATCH + "new file mode 100644\n", ["app/access.py"], 0),
    ]
    for target, patch, files, attempt in cases:
        assert not validate_patch(target, patch, files, attempt, settings).allowed


def test_size_and_file_limits(setup):
    _, _, _, settings = setup
    assert not validate_patch("bola-demo-v1", PATCH * 400, ["app/access.py"], 0, settings).allowed
    assert not validate_patch("bola-demo-v1", PATCH + PATCH, ["app/access.py", "app/access.py"],
                              0, settings).allowed
