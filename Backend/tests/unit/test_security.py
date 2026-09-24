import pytest

from sonora.security import (
    MAX_PASSWORD_LENGTH,
    PasswordHasher,
    new_token,
    password_problem,
    token_digest,
    tokens_match,
)


def test_tokens_are_random_url_safe_and_long() -> None:
    tokens = {new_token() for _ in range(100)}
    assert len(tokens) == 100
    assert all(len(t) >= 43 and t.replace("-", "").replace("_", "").isalnum() for t in tokens)


def test_token_digest_is_a_stable_sha256() -> None:
    assert token_digest("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert token_digest("abc") != token_digest("abd")


def test_tokens_match_is_exact() -> None:
    assert tokens_match("secret", "secret")
    assert not tokens_match("secret", "Secret")
    assert not tokens_match("secret", "")


class TestPasswordHasher:
    @pytest.fixture
    def hasher(self) -> PasswordHasher:
        return PasswordHasher(time_cost=1, memory_cost_kib=8, parallelism=1)

    async def test_hash_and_verify(self, hasher: PasswordHasher) -> None:
        hashed = await hasher.hash("correct horse battery staple")
        assert hashed.startswith("$argon2id$")
        assert await hasher.verify(hashed, "correct horse battery staple")
        assert not await hasher.verify(hashed, "correct horse battery stapl")

    async def test_missing_or_corrupt_hashes_never_verify(self, hasher: PasswordHasher) -> None:
        assert not await hasher.verify(None, "anything")  # unknown account: dummy hash is used
        assert not await hasher.verify("not-a-hash", "anything")

    async def test_needs_rehash_when_parameters_change(self, hasher: PasswordHasher) -> None:
        hashed = await hasher.hash("pw")
        assert not hasher.needs_rehash(hashed)
        stronger = PasswordHasher(time_cost=2, memory_cost_kib=16, parallelism=1)
        assert stronger.needs_rehash(hashed)


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("short", "at least 12"),
        ("x" * (MAX_PASSWORD_LENGTH + 1), "at most"),
        ("abababababababab", "too simple"),
        ("qwertzuiopasdf", "easy to guess"),
        ("6543210987654", "easy to guess"),  # reversed run
        ("Passwort2026!!", "too common"),
        ("sonora_1234567", "too common"),
        ("my-marie.tanner-pw", "email"),
    ],
)
def test_password_policy_rejects(password: str, expected: str) -> None:
    problem = password_problem(password, min_length=12, email="marie.tanner@example.com")
    assert problem is not None and expected in problem


@pytest.mark.parametrize(
    "password",
    ["violet-harbor-lantern-42", "Zugspitze im Nebel 2026", "ünïcödé pässwörds wörk"],
)
def test_password_policy_accepts_reasonable_passphrases(password: str) -> None:
    assert password_problem(password, min_length=12, email="marie@example.com") is None
