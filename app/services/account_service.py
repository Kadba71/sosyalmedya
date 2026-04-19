from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import AccountConnectionState, Platform, Project, PublishProfile, SocialAccount, User
from app.schemas.api import ConnectAccountRequest, PublishProfileCreate
from app.utils.security import TokenCipher


class AccountService:
    def __init__(self, session: Session, cipher: TokenCipher) -> None:
        self.session = session
        self.cipher = cipher

    def connect_account(self, user: User, payload: ConnectAccountRequest) -> SocialAccount:
        platform = Platform(payload.platform)
        account = (
            self.session.query(SocialAccount)
            .filter(
                SocialAccount.user_id == user.id,
                SocialAccount.platform == platform,
                SocialAccount.external_account_id == payload.external_account_id,
            )
            .one_or_none()
        )
        if account is None:
            account = SocialAccount(
                user_id=user.id,
                platform=platform,
                display_name=payload.display_name,
                external_account_id=payload.external_account_id,
            )
            self.session.add(account)

        account.access_token_encrypted = self.cipher.encrypt(payload.access_token)
        account.refresh_token_encrypted = self.cipher.encrypt(payload.refresh_token)
        account.scopes = payload.scopes
        account.state = self._resolve_account_state(payload.access_token, payload.expires_at)
        account.expires_at = payload.expires_at
        account.metadata_payload = payload.metadata_payload
        self.session.commit()
        self.session.refresh(account)
        return account

    def create_publish_profile(self, project: Project, payload: PublishProfileCreate) -> PublishProfile:
        profile = PublishProfile(
            project_id=project.id,
            name=payload.name,
            description=payload.description,
            account_ids=payload.account_ids,
            platform_overrides=payload.platform_overrides,
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def refresh_account_state(self, account: SocialAccount, *, expires_at: datetime | None = None) -> SocialAccount:
        account.state = self._resolve_account_state(self.cipher.decrypt(account.access_token_encrypted), expires_at)
        account.expires_at = expires_at
        self.session.commit()
        self.session.refresh(account)
        return account

    @staticmethod
    def _resolve_account_state(access_token: str | None, expires_at: datetime | None) -> AccountConnectionState:
        if not access_token:
            return AccountConnectionState.PENDING
        if expires_at and expires_at <= datetime.utcnow():
            return AccountConnectionState.REAUTH_REQUIRED
        return AccountConnectionState.ACTIVE
