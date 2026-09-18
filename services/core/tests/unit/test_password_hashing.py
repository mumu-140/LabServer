from labserver_core.application.passwords import Argon2PasswordHasher


def test_hash_verify_round_trip() -> None:
    hasher = Argon2PasswordHasher()
    encoded = hasher.hash("correct horse battery staple")
    assert hasher.verify("correct horse battery staple", encoded) is True


def test_wrong_password_fails_to_verify() -> None:
    hasher = Argon2PasswordHasher()
    encoded = hasher.hash("correct horse battery staple")
    assert hasher.verify("wrong password", encoded) is False


def test_verify_against_garbage_fails_cleanly() -> None:
    hasher = Argon2PasswordHasher()
    assert hasher.verify("anything", "not-a-hash") is False


def test_hashes_are_salted() -> None:
    hasher = Argon2PasswordHasher()
    first = hasher.hash("same raw password")
    second = hasher.hash("same raw password")
    assert first != second
    assert hasher.verify("same raw password", first)
    assert hasher.verify("same raw password", second)
