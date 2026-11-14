"""Print production candidates for audit records whose exact content did not match."""

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.entities import Question

LOOKUPS = {
    36: ["Email", "이메일 주소", "데이터 품질 규칙"],
    147: ["cities_world", "cities_us"],
    177: ["old-table", "새 빈 테이블"],
    296: ["load_date", "구체화된 뷰"],
}


def main() -> None:
    with SessionLocal() as db:
        for source_no, terms in LOOKUPS.items():
            conditions = [Question.question_ko.ilike(f"%{term}%") for term in terms]
            rows = list(db.scalars(
                select(Question)
                .where(or_(*conditions))
                .options(selectinload(Question.choices))
                .order_by(Question.id)
            ))
            print(f"\n=== SOURCE {source_no}: {len(rows)} candidate(s) ===")
            for question in rows:
                print(f"ID={question.id} UID={question.question_uid} STATUS={question.verification_status}")
                print(question.question_ko)
                for choice in question.choices:
                    print(f"{choice.choice_key}. {choice.text_ko}")


if __name__ == "__main__":
    main()
