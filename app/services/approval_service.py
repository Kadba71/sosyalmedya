from sqlalchemy.orm import Session

from app.db.models import Approval, ApprovalAction, ApprovalTarget, Niche, NicheStatus, Prompt, PromptStatus, Video, VideoStatus


class ApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def apply(self, *, target_type: ApprovalTarget, target_id: int, action: ApprovalAction, notes: str = "") -> Approval:
        target = None
        if target_type == ApprovalTarget.NICHE:
            target = self.session.get(Niche, target_id)
        elif target_type == ApprovalTarget.PROMPT:
            target = self.session.get(Prompt, target_id)
        elif target_type == ApprovalTarget.VIDEO:
            target = self.session.get(Video, target_id)
        if target is None:
            raise ValueError(f"Target not found: {target_type.value}#{target_id}")

        approval = Approval(target_type=target_type, target_id=target_id, action=action, notes=notes)
        self.session.add(approval)

        if target_type == ApprovalTarget.NICHE:
            target.status = NicheStatus.APPROVED if action == ApprovalAction.APPROVE else NicheStatus.ARCHIVED
        elif target_type == ApprovalTarget.PROMPT:
            if action == ApprovalAction.APPROVE:
                target.status = PromptStatus.APPROVED
            elif action == ApprovalAction.REJECT:
                target.status = PromptStatus.REJECTED
        elif target_type == ApprovalTarget.VIDEO:
            if action == ApprovalAction.APPROVE:
                target.status = VideoStatus.APPROVED
            elif action == ApprovalAction.REJECT:
                target.status = VideoStatus.REJECTED

        self.session.commit()
        self.session.refresh(approval)
        return approval
