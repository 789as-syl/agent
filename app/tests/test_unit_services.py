"""测试模块：test_unit_services。"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.models.conversation import Conversation
from app.models.user import User, UserRole, UserStatus
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService


class TestAuthService:
    """Tests for AuthService."""

    @pytest.mark.asyncio
    async def test_register_success(self, db_session: AsyncSession, mock_redis):
        """Test successful user registration."""
        service = AuthService(db_session)

        user = await service.register(
            phone="13900000001",
            password="TestPass123",
        )

        assert user.id is not None
        assert user.phone == "13900000001"
        assert user.password_hash != "TestPass123"

    @pytest.mark.asyncio
    async def test_register_duplicate_phone(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test registration with duplicate phone."""
        service = AuthService(db_session)

        with pytest.raises(ValidationError) as exc:
            await service.register(
                phone=test_user.phone,
                password="TestPass123",
            )

        assert exc.value.error_code == "USER_ALREADY_EXISTS"

    @pytest.mark.asyncio
    async def test_authenticate_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test successful authentication."""
        service = AuthService(db_session)

        user = await service.authenticate(
            phone=test_user.phone,
            password="TestPass123",
        )

        assert user.id == test_user.id
        assert user.phone == test_user.phone

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test authentication with wrong password."""
        service = AuthService(db_session)

        with pytest.raises(ValidationError) as exc:
            await service.authenticate(
                phone=test_user.phone,
                password="WrongPassword123",
            )

        assert exc.value.error_code == "AUTH_INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, db_session: AsyncSession):
        """Test authentication with non-existent user."""
        service = AuthService(db_session)

        with pytest.raises(ValidationError) as exc:
            await service.authenticate(
                phone="13999999999",
                password="TestPass123",
            )

        assert exc.value.error_code == "AUTH_INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_authenticate_disabled_account(
        self,
        db_session: AsyncSession,
    ):
        """Test authentication with disabled account."""
        from app.core.security import hash_password

        user = User(
            id=uuid4(),
            phone="13900000002",
            password_hash=hash_password("TestPass123"),
            role=UserRole.USER,
            status=UserStatus.DISABLED,
        )
        db_session.add(user)
        await db_session.flush()

        service = AuthService(db_session)

        with pytest.raises(ValidationError) as exc:
            await service.authenticate(
                phone="13900000002",
                password="TestPass123",
            )

        assert exc.value.error_code == "AUTH_ACCOUNT_DISABLED"

    @pytest.mark.asyncio
    async def test_get_user_by_id_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting user by ID."""
        service = AuthService(db_session)

        user = await service.get_user_by_id(test_user.id)

        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        """Test getting non-existent user by ID."""
        service = AuthService(db_session)

        with pytest.raises(NotFoundError):
            await service.get_user_by_id(uuid4())


class TestConversationService:
    """Tests for ConversationService."""

    @pytest.mark.asyncio
    async def test_list_conversations_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test listing conversations."""
        conv1 = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Conv 1",
            is_deleted=False,
        )
        conv2 = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Conv 2",
            is_deleted=False,
        )
        db_session.add_all([conv1, conv2])
        await db_session.flush()

        service = ConversationService(db_session)
        items, total = await service.list_conversations(test_user.id)

        assert total >= 2
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_create_conversation_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test creating a conversation."""
        service = ConversationService(db_session)

        conv = await service.create_conversation(
            user_id=test_user.id,
            title="New Conversation",
        )

        assert conv.id is not None
        assert conv.user_id == test_user.id
        assert conv.title == "New Conversation"

    @pytest.mark.asyncio
    async def test_create_conversation_title_too_long(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test creating conversation with title too long."""
        service = ConversationService(db_session)

        with pytest.raises(ValidationError) as exc:
            await service.create_conversation(
                user_id=test_user.id,
                title="a" * 300,
            )

        assert exc.value.error_code == "CONVERSATION_TITLE_TOO_LONG"

    @pytest.mark.asyncio
    async def test_get_conversation_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting a conversation."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Test Conv",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        service = ConversationService(db_session)
        result = await service.get_conversation(test_user.id, conv.id)

        assert result.id == conv.id

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting non-existent conversation."""
        service = ConversationService(db_session)

        with pytest.raises(NotFoundError):
            await service.get_conversation(test_user.id, uuid4())

    @pytest.mark.asyncio
    async def test_get_conversation_permission_denied(
        self,
        db_session: AsyncSession,
        other_user: User,
    ):
        """Test getting conversation belonging to another user."""
        conv = Conversation(
            id=uuid4(),
            user_id=other_user.id,
            title="Other Conv",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        service = ConversationService(db_session)

        with pytest.raises(PermissionDeniedError):
            await service.get_conversation(uuid4(), conv.id)

    @pytest.mark.asyncio
    async def test_update_title_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test updating conversation title."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Old Title",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        service = ConversationService(db_session)
        result = await service.update_title(
            user_id=test_user.id,
            conversation_id=conv.id,
            new_title="New Title",
        )

        assert result.title == "New Title"

    @pytest.mark.asyncio
    async def test_delete_conversation_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test deleting a conversation."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="To Delete",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        service = ConversationService(db_session)
        await service.delete_conversation(test_user.id, conv.id)

        await db_session.refresh(conv)
        assert conv.is_deleted is True

    @pytest.mark.asyncio
    async def test_restore_conversation_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test restoring a deleted conversation."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Deleted",
            is_deleted=True,
        )
        db_session.add(conv)
        await db_session.flush()

        service = ConversationService(db_session)
        result = await service.restore_conversation(
            user_id=test_user.id,
            conversation_id=conv.id,
        )

        assert result.is_deleted is False
