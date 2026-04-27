"""Tests for password hashing helpers."""

from app.core.security import hash_password, verify_password


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_success(self) -> None:
        """Test successful password hashing."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) > 50

    def test_hash_password_different_salts(self) -> None:
        """Test that same password produces different hashes."""
        password = "TestPassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2

    def test_verify_password_correct(self) -> None:
        """Test password verification with correct password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Test password verification with incorrect password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password("WrongPassword", hashed) is False

    def test_verify_password_empty(self) -> None:
        """Test password verification with empty password."""
        password = "TestPassword123"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

    def test_hash_password_empty(self) -> None:
        """Test hashing empty password."""
        hashed = hash_password("")
        assert hashed.startswith("$2b$")
