from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.router import create_study
from app.db.base import Base
from app.models.entities import (
    Certification,
    Domain,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
    StudyAttempt,
    User,
)
from app.schemas.api import StudySessionCreate


def test_study_orders_each_users_unseen_questions_before_seen_questions() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="데이터",
            exam_version="v1", default_question_count=3,
            default_duration_minutes=10, passing_score=70,
        )
        user_a = User(username="learner-a", password_hash="hash")
        user_b = User(username="learner-b", password_hash="hash")
        db.add_all((certification, user_a, user_b)); db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="D1", name_en="D1",
            name_ko="D1", exam_weight=100,
        )
        db.add(domain); db.flush()
        questions: list[Question] = []
        for index in range(3):
            question = Question(
                question_uid=f"unseen-{index}", certification_id=certification.id,
                domain_id=domain.id, question_type="multiple_choice",
                question_en=f"Question {index}", question_ko=f"문제 {index}",
                content_hash=f"unseen-hash-{index}", verification_status="verified",
                choices=[QuestionChoice(choice_key="A", text_en="A", sort_order=1)],
                answer_versions=[QuestionAnswerVersion(
                    answer_source="admin_final", answers_json=["A"], is_current=True,
                )],
            )
            db.add(question); questions.append(question)
        db.flush()
        db.add_all((
            StudyAttempt(
                user_id=user_a.id, session_id="old-a", question_id=questions[0].id,
                selected_answers_json=["A"], is_correct=True,
            ),
            StudyAttempt(
                user_id=user_b.id, session_id="old-b", question_id=questions[1].id,
                selected_answers_json=["A"], is_correct=True,
            ),
        ))
        db.commit()

        payload = StudySessionCreate(
            certification_code="DEA-C01", mode="random", question_count=3, seed=7,
        )
        session_a = create_study(payload, db, user_a)
        session_b = create_study(payload, db, user_b)

        assert session_a.question_ids[-1] == questions[0].id
        assert session_b.question_ids[-1] == questions[1].id
        assert set(session_a.question_ids) == {question.id for question in questions}
        assert set(session_b.question_ids) == {question.id for question in questions}
