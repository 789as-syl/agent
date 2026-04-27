"""测试模块：test_unit_repositories。"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.question_bank import Question, QuestionType
from app.models.user import User, UserRole, UserStatus
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.question_repo import QuestionRepository
from app.repositories.user_repo import UserRepository


class TestUserRepository:
    """Tests for User repository."""

    @pytest.mark.asyncio
    async def test_get_by_id_success(self, db_session: AsyncSession, test_user: User):
        """Test getting user by ID."""
        repo = UserRepository(db_session)
        user = await repo.get_by_id(test_user.id)

        assert user is not None
        assert user.id == test_user.id
        assert user.phone == test_user.phone

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """Test getting non-existent user by ID."""
        repo = UserRepository(db_session)
        user = await repo.get_by_id(uuid4())

        assert user is None

    @pytest.mark.asyncio
    async def test_get_by_phone_success(self, db_session: AsyncSession, test_user: User):
        """Test getting user by phone."""
        repo = UserRepository(db_session)
        user = await repo.get_by_phone(test_user.phone)

        assert user is not None
        assert user.phone == test_user.phone

    @pytest.mark.asyncio
    async def test_get_by_phone_not_found(self, db_session: AsyncSession):
        """Test getting user by non-existent phone."""
        repo = UserRepository(db_session)
        user = await repo.get_by_phone("13999999999")

        assert user is None

    @pytest.mark.asyncio
    async def test_create_user_success(self, db_session: AsyncSession):
        """Test creating a new user."""
        repo = UserRepository(db_session)
        user = await repo.create(
            phone="13900000001",
            password_hash="hashed_password",
        )

        assert user.id is not None
        assert user.phone == "13900000001"
        assert user.role == UserRole.USER
        assert user.status == UserStatus.ACTIVE


class TestConversationRepository:
    """Tests for Conversation repository."""

    @pytest.mark.asyncio
    async def test_list_by_user_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test listing conversations by user."""
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

        repo = ConversationRepository(db_session)
        items, total = await repo.list_by_user(test_user.id, skip=0, limit=10)

        assert total >= 2
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_get_by_user_and_id_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test getting conversation by user and ID."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Test Conv",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        repo = ConversationRepository(db_session)
        result = await repo.get_by_user_and_id(test_user.id, conv.id)

        assert result is not None
        assert result.id == conv.id

    @pytest.mark.asyncio
    async def test_get_by_user_and_id_wrong_user(
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

        repo = ConversationRepository(db_session)
        result = await repo.get_by_user_and_id(uuid4(), conv.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_create_conversation_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test creating a new conversation."""
        repo = ConversationRepository(db_session)
        conv = await repo.create(user_id=test_user.id, title="New Conv")

        assert conv.id is not None
        assert conv.user_id == test_user.id
        assert conv.title == "New Conv"
        assert conv.is_deleted is False

    @pytest.mark.asyncio
    async def test_soft_delete_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test soft deleting a conversation."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="To Delete",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        repo = ConversationRepository(db_session)
        await repo.soft_delete(conv)

        assert conv.is_deleted is True


class TestMessageRepository:
    """Tests for Message repository."""

    @pytest.mark.asyncio
    async def test_list_by_conversation_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test listing messages by conversation."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Conv",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        msg1 = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="user",
            content="Hello",
        )
        msg2 = Message(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content="Hi",
        )
        db_session.add_all([msg1, msg2])
        await db_session.flush()

        repo = MessageRepository(db_session)
        items, total = await repo.list_by_conversation(conv.id, skip=0, limit=10)

        assert total >= 2
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_create_message_success(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test creating a new message."""
        conv = Conversation(
            id=uuid4(),
            user_id=test_user.id,
            title="Conv",
            is_deleted=False,
        )
        db_session.add(conv)
        await db_session.flush()

        repo = MessageRepository(db_session)
        msg = await repo.create(
            conversation_id=conv.id,
            role="user",
            content="Test message",
        )

        assert msg.id is not None
        assert msg.conversation_id == conv.id
        assert msg.role == "user"
        assert msg.content == "Test message"


class TestQuestionRepository:
    """Tests for Question repository."""

    @pytest.mark.asyncio
    async def test_get_by_id_success(
        self,
        db_session: AsyncSession,
        test_question_bank,
    ):
        """Test getting question by ID."""
        q = Question(
            id=uuid4(),
            question_text="Test Question",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=test_question_bank.id,
            content_hash="hash",
            is_dirty=True,
        )
        db_session.add(q)
        await db_session.flush()

        repo = QuestionRepository(db_session)
        result = await repo.get_by_id(q.id)

        assert result is not None
        assert result.id == q.id

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """Test getting non-existent question."""
        repo = QuestionRepository(db_session)
        result = await repo.get_by_id(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_list_questions_success(
        self,
        db_session: AsyncSession,
        test_question_bank,
    ):
        """Test listing questions."""
        q1 = Question(
            id=uuid4(),
            question_text="Q1",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=test_question_bank.id,
            content_hash="hash1",
            is_dirty=True,
        )
        q2 = Question(
            id=uuid4(),
            question_text="Q2",
            question_type=QuestionType.SINGLE,
            answer="B",
            bank_id=test_question_bank.id,
            content_hash="hash2",
            is_dirty=True,
        )
        db_session.add_all([q1, q2])
        await db_session.flush()

        repo = QuestionRepository(db_session)
        items, total = await repo.list_questions(page=1, page_size=10)

        assert total >= 2
        assert len(items) >= 2

    @pytest.mark.asyncio
    async def test_create_question_success(
        self,
        db_session: AsyncSession,
        test_question_bank,
    ):
        """Test creating a new question."""
        repo = QuestionRepository(db_session)
        q = await repo.create(
            question_text="New Question",
            question_type=QuestionType.SINGLE,
            answer="A",
            bank_id=test_question_bank.id,
            content_hash="hash",
            is_dirty=True,
        )

        assert q.id is not None
        assert q.question_text == "New Question"
