from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Project, User


def bootstrap_single_user(session: Session, settings: Settings) -> tuple[User, Project]:
    user = session.query(User).filter(User.telegram_user_id == settings.default_telegram_user_id).one_or_none()
    if user is None:
        user = session.query(User).order_by(User.id.asc()).first()
    if user is None:
        user = User(
            telegram_user_id=settings.default_telegram_user_id,
            telegram_chat_id=settings.default_telegram_chat_id,
            display_name="Owner",
            timezone=settings.default_timezone,
        )
        session.add(user)
        session.flush()

    project = session.query(Project).filter(Project.user_id == user.id).one_or_none()
    if project is None:
        project = Project(user_id=user.id, name="TR Trend Video Automation", market="tr-TR")
        session.add(project)
        session.flush()

    session.commit()
    return user, project
