import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ApprovalAction, ApprovalTarget, EditRequest, Niche, Platform, Prompt, PromptStatus, SocialAccount, User, Video, VideoStatus
from app.schemas.api import TelegramWebhookPayload
from app.services.account_validation_service import AccountValidationService
from app.services.approval_service import ApprovalService
from app.services.bootstrap import bootstrap_single_user
from app.services.cover_workflow_service import CoverWorkflowService
from app.services.edit_service import EditService
from app.services.oauth_service import OAuthService
from app.services.orchestrator import OrchestratorService
from app.utils.security import TokenCipher


class TelegramBotService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.approvals = ApprovalService(session)
        self.orchestrator = OrchestratorService(session, settings)
        self.account_validator = AccountValidationService(settings, TokenCipher(settings))
        self.oauth = OAuthService(settings)
        self.editor = EditService(session, settings)
        self.covers = CoverWorkflowService(session, settings)

    def handle_update(self, payload: TelegramWebhookPayload) -> dict:
        user, project = bootstrap_single_user(self.session, self.settings)
        user = self._sync_user_from_payload(payload, user)
        if payload.callback_query:
            return self._handle_callback_query(payload.callback_query)
        text = self._extract_text(payload)
        if not text:
            return {"message": "No command found in payload."}

        if text == "/start":
            return {"message": self._help_message(user.display_name, project.name)}
        if text == "/help":
            return {"message": self._help_message(user.display_name, project.name)}
        try:
            if text == "/scan":
                niches = self.orchestrator.daily_scan(project)
                niche_names = [niche.name for niche in niches]
                lines = [f"{len(niches)} trend nis bulundu."]
                if niche_names:
                    lines.append("")
                    lines.append("Bulunan nisler:")
                    lines.extend(f"- {name}" for name in niche_names)
                return {"message": "\n".join(lines), "niches": niche_names}
            if text.startswith("/prompts"):
                return self._prompts_command(text)
            if text.startswith("/video"):
                return self._video_command(text)
            if text.startswith("/approve"):
                return self._approval_command(text, ApprovalAction.APPROVE)
            if text.startswith("/reject"):
                return self._approval_command(text, ApprovalAction.REJECT)
            if text == "/status":
                return {
                    "message": "Durum ozeti hazir.",
                    "niche_count": self.session.query(Niche).count(),
                    "prompt_count": self.session.query(Prompt).count(),
                    "video_count": self.session.query(Video).count(),
                }
            if text == "/accounts":
                return self._accounts_summary(user)
            if text.startswith("/history"):
                return self._history_command(text)
            if text.startswith("/connect"):
                return self._connect_command(text)
            if text.startswith("/validate_account"):
                return self._validate_account_command(user, text)
            if text.startswith("/publish_check"):
                return self._publish_check_command(user, text)
            if text.startswith("/publish"):
                return self._publish_command(user, text)
            if text.startswith("/edit_prompt"):
                return self._edit_prompt_command(text)
            if text.startswith("/regenerate_prompt"):
                return self._regenerate_prompt_command(text)
            if text.startswith("/edit_video"):
                return self._edit_video_command(text)
            if text.startswith("/regenerate_video"):
                return self._regenerate_video_command(text)
            if text.startswith("/merge_video"):
                return self._merge_video_command(text)
            if text.startswith("/cover_prompts"):
                return self._cover_prompts_command(text)
            if text.startswith("/approve_cover_prompt"):
                return self._approve_cover_prompt_command(text)
            if text.startswith("/generate_covers"):
                return self._generate_covers_command(text)
        except ValueError as exc:
            return {"message": str(exc)}
        except Exception:
            return {"message": "Komut islenirken beklenmeyen bir hata olustu."}
        return {"message": f"Komut taninmadi: {text}"}

    def send_reply(self, payload: TelegramWebhookPayload, result: dict) -> None:
        chat_id = self._extract_chat_id(payload)
        message = result.get("message")
        if not self.settings.telegram_bot_token:
            return
        callback_query = payload.callback_query or {}
        callback_id = callback_query.get("id")
        if callback_id:
            callback_text = str(result.get("callback_message") or message or "Islem tamamlandi.")[:200]
            httpx.post(
                f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": callback_text},
                timeout=30,
            )
        if not chat_id or not message:
            return

        payload_json = {
            "chat_id": chat_id,
            "text": str(message),
            "disable_web_page_preview": False,
        }
        if result.get("reply_markup"):
            payload_json["reply_markup"] = result["reply_markup"]
        if result.get("photo_url"):
            httpx.post(
                f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendPhoto",
                json={"chat_id": chat_id, "photo": result["photo_url"], "caption": str(message)},
                timeout=30,
            )
            return
        httpx.post(
            f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage",
            json=payload_json,
            timeout=30,
        )

    def _accounts_summary(self, user: User) -> dict:
        accounts = self.session.query(SocialAccount).filter(SocialAccount.user_id == user.id).order_by(SocialAccount.platform, SocialAccount.id).all()
        if not accounts:
            return {"message": "Bagli sosyal hesap yok. /connect youtube KanalAdi gibi komutla baglanti baslatin."}
        lines = ["Bagli hesaplar:"]
        for account in accounts:
            lines.append(f"- {account.id} | {account.platform.value} | {account.display_name} | {account.state.value}")
        lines.append("Dogrulama icin: /validate_account <account_id>")
        lines.append("Yayin kontrolu icin: /publish_check <video_id> <account_id>")
        return {"message": "\n".join(lines), "account_ids": [item.id for item in accounts]}

    def _connect_command(self, text: str) -> dict:
        parts = text.split(maxsplit=3)
        if len(parts) < 3:
            raise ValueError("Kullanim: /connect <youtube|instagram|facebook|tiktok> <gorunen_ad> [external_account_id]")
        _, platform_name, display_name, *rest = parts
        external_account_id = rest[0] if rest else None
        try:
            details = self.oauth.build_connect_details(
                platform_name=platform_name.lower(),
                display_name=display_name,
                external_account_id=external_account_id,
            )
        except ValueError as exc:
            return {"message": f"Baglanti hazirlanamadi: {exc}"}
        return {
            "message": (
                f"{platform_name} baglanti linki hazir:\n{details['authorization_url']}\n\n"
                "Baglantiyi tamamladiktan sonra hesap otomatik kaydolur. Hesaplari gormek icin /accounts kullanin."
            ),
            "authorization_url": details["authorization_url"],
        }

    def _validate_account_command(self, user: User, text: str) -> dict:
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError("Kullanim: /validate_account <account_id>")
        account = (
            self.session.query(SocialAccount)
            .filter(SocialAccount.user_id == user.id, SocialAccount.id == int(parts[1]))
            .one_or_none()
        )
        if account is None:
            return {"message": "Hesap bulunamadi."}
        result = self.account_validator.validate_account(account, remote_check=True)
        lines = [
            f"Hesap: {account.display_name} ({account.platform.value})",
            f"Durum: {'hazir' if result.get('valid') else 'eksik'}",
            f"Token: {'var' if result.get('token_present') else 'yok'}",
        ]
        for key, value in result.get("metadata_checks", {}).items():
            lines.append(f"{key}: {'ok' if value else 'eksik'}")
        if result.get("error"):
            lines.append(f"Hata: {result['error']}")
        return {"message": "\n".join(lines), "validation": result}

    def _publish_check_command(self, user: User, text: str) -> dict:
        parts = text.split(maxsplit=2)
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            raise ValueError("Kullanim: /publish_check <video_id> <account_id>")
        video = self.session.get(Video, int(parts[1]))
        if video is None:
            return {"message": "Video bulunamadi."}
        account = (
            self.session.query(SocialAccount)
            .filter(SocialAccount.user_id == user.id, SocialAccount.id == int(parts[2]))
            .one_or_none()
        )
        if account is None:
            return {"message": "Hesap bulunamadi."}
        result = self.account_validator.validate_publish_readiness(video=video, account=account)
        lines = [
            f"Publish kontrolu: video {video.id} -> hesap {account.id}",
            f"Platform: {account.platform.value}",
            f"Hazirlik: {'tamam' if result.get('publish_ready') else 'eksik'}",
        ]
        if result.get("video_url"):
            lines.append(f"Video URL: {result['video_url']}")
        for key, value in result.get("status_checks", {}).items():
            lines.append(f"{key}: {'ok' if value else 'eksik'}")
        for key, value in result.get("metadata_checks", {}).items():
            lines.append(f"{key}: {'ok' if value else 'eksik'}")
        if result.get("error"):
            lines.append(f"Hata: {result['error']}")
        if result.get("video_error"):
            lines.append(f"Video: {result['video_error']}")
        return {"message": "\n".join(lines), "validation": result}

    def _publish_command(self, user: User, text: str) -> dict:
        parts = text.split(maxsplit=3)
        if len(parts) < 3 or not parts[1].isdigit() or not parts[2].isdigit():
            raise ValueError("Kullanim: /publish <video_id> <account_id> [caption]")
        video = self.session.get(Video, int(parts[1]))
        if video is None:
            return {"message": "Video bulunamadi."}
        account = (
            self.session.query(SocialAccount)
            .filter(SocialAccount.user_id == user.id, SocialAccount.id == int(parts[2]))
            .one_or_none()
        )
        if account is None:
            return {"message": "Hesap bulunamadi."}
        caption = parts[3] if len(parts) == 4 else ""
        readiness = self.account_validator.validate_publish_readiness(video=video, account=account)
        if not readiness.get("publish_ready"):
            return {
                "message": (
                    "Yayin baslatilamadi. Once /publish_check komutunu kullanin ve eksikleri giderin.\n"
                    f"Detay: {readiness.get('error') or readiness.get('video_error') or 'validation_failed'}"
                ),
                "validation": readiness,
            }
        publications = self.orchestrator.publish_video(video=video, accounts=[account], caption=caption, platform_overrides={})
        publication = publications[0]
        lines = [
            f"Yayin denemesi tamamlandi: publication {publication.id}",
            f"Platform: {account.platform.value}",
            f"Durum: {publication.status.value}",
        ]
        if publication.platform_url:
            lines.append(f"URL: {publication.platform_url}")
        if publication.error_message:
            lines.append(f"Hata: {publication.error_message}")
        return {"message": "\n".join(lines), "publication_id": publication.id, "status": publication.status.value}

    def _prompts_command(self, text: str) -> dict:
        niche_id = self._parse_single_int_argument(text, command="/prompts")
        niche = self.session.get(Niche, niche_id)
        if niche is None:
            raise ValueError("Niche bulunamadi.")
        prompts = self.orchestrator.generate_prompts(niche)
        return {"message": f"{len(prompts)} prompt uretildi.", "prompt_ids": [prompt.id for prompt in prompts]}

    def _video_command(self, text: str) -> dict:
        prompt_id = self._parse_single_int_argument(text, command="/video")
        prompt = self.session.get(Prompt, prompt_id)
        if prompt is None:
            raise ValueError("Prompt bulunamadi.")
        video = self.orchestrator.request_video(prompt)
        return self._video_approval_card(video, prefix="Video istegi olusturuldu.")

    def _history_command(self, text: str) -> dict:
        parts = text.split(maxsplit=2)
        if len(parts) != 3 or not parts[2].isdigit():
            raise ValueError("Kullanim: /history <prompt|video> <id>")

        target_name = parts[1].strip().lower()
        target_id = int(parts[2])
        if target_name == "prompt":
            prompt = self.session.get(Prompt, target_id)
            if prompt is None:
                return {"message": "Prompt bulunamadi."}
            return {"message": self._build_prompt_history_message(prompt), "prompt_id": prompt.id}
        if target_name == "video":
            video = self.session.get(Video, target_id)
            if video is None:
                return {"message": "Video bulunamadi."}
            return {"message": self._build_video_history_message(video), "video_id": video.id}
        raise ValueError("Kullanim: /history <prompt|video> <id>")

    def _edit_prompt_command(self, text: str) -> dict:
        prompt_id, instruction = self._parse_id_and_instruction(text, command="/edit_prompt")
        prompt = self.session.get(Prompt, prompt_id)
        if prompt is None:
            return {"message": "Prompt bulunamadi."}
        edit_request, revised_prompt = self.editor.revise_prompt(prompt, instruction)
        result = self._prompt_approval_card(revised_prompt, prefix="Prompt revize edildi.")
        result["edit_request_id"] = edit_request.id
        return result

    def _regenerate_prompt_command(self, text: str) -> dict:
        prompt_id = self._parse_single_int_argument(text, command="/regenerate_prompt")
        prompt = self.session.get(Prompt, prompt_id)
        if prompt is None:
            return {"message": "Prompt bulunamadi."}
        revised_prompt = self.editor.regenerate_prompt(prompt)
        return self._prompt_approval_card(revised_prompt, prefix="Prompt yeniden uretildi.")

    def _edit_video_command(self, text: str) -> dict:
        video_id, instruction = self._parse_id_and_instruction(text, command="/edit_video")
        video = self.session.get(Video, video_id)
        if video is None:
            return {"message": "Video bulunamadi."}
        edit_request, revised_video = self.editor.revise_video(video, instruction)
        result = self._video_approval_card(revised_video, prefix="Video revize istegi olusturuldu.")
        result["edit_request_id"] = edit_request.id
        return result

    def _regenerate_video_command(self, text: str) -> dict:
        video_id = self._parse_single_int_argument(text, command="/regenerate_video")
        video = self.session.get(Video, video_id)
        if video is None:
            return {"message": "Video bulunamadi."}
        revised_video = self.editor.regenerate_video(video)
        return self._video_approval_card(revised_video, prefix="Video yeniden uretim istegi olusturuldu.")

    def _merge_video_command(self, text: str) -> dict:
        video_id = self._parse_single_int_argument(text, command="/merge_video")
        video = self.session.get(Video, video_id)
        if video is None:
            return {"message": "Video bulunamadi."}
        try:
            merged_video = self.orchestrator.merge_video_segments(video)
        except Exception as exc:
            return {"message": f"Video birlestirilemedi: {exc}"}
        return {
            "message": (
                f"Video birlestirildi. Video ID: {merged_video.id}\n"
                f"Birlesik dosya: {merged_video.storage_path}\n"
                "Not: Yayin icin hala public URL veya object storage yuklemesi gerekebilir."
            ),
            "video_id": merged_video.id,
        }

    def _cover_prompts_command(self, text: str) -> dict:
        video_id = self._parse_single_int_argument(text, command="/cover_prompts")
        video = self.session.get(Video, video_id)
        if video is None:
            return {"message": "Video bulunamadi."}
        self.covers.generate_cover_prompts(video)
        self.session.refresh(video)
        return self._cover_prompt_card(video, prefix="Platform kapak promptlari hazirlandi.")

    def _approve_cover_prompt_command(self, text: str) -> dict:
        video_id = self._parse_single_int_argument(text, command="/approve_cover_prompt")
        video = self.session.get(Video, video_id)
        if video is None:
            return {"message": "Video bulunamadi."}
        self.covers.approve_cover_prompts(video)
        self.session.refresh(video)
        return self._cover_prompt_card(video, prefix="Kapak promptlari onaylandi.")

    def _generate_covers_command(self, text: str) -> dict:
        video_id = self._parse_single_int_argument(text, command="/generate_covers")
        video = self.session.get(Video, video_id)
        if video is None:
            return {"message": "Video bulunamadi."}
        try:
            assets = self.covers.generate_cover_images(video)
        except Exception as exc:
            return {"message": f"Kapak gorselleri uretilemedi: {exc}"}
        return self._cover_assets_message(video_id, assets, prefix="Kapak gorselleri uretildi.")

    def _handle_callback_query(self, callback_query: dict) -> dict:
        data = str(callback_query.get("data") or "")
        parts = data.split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            return {"message": "Gecersiz buton islemi.", "callback_message": "Gecersiz istek."}
        action_name, target_name, raw_id = parts
        target_id = int(raw_id)
        try:
            target_type = ApprovalTarget(target_name)
        except ValueError:
            return {"message": "Gecersiz hedef tipi.", "callback_message": "Gecersiz hedef."}

        if action_name == "approve":
            approval = self.approvals.apply(target_type=target_type, target_id=target_id, action=ApprovalAction.APPROVE)
            if target_type == ApprovalTarget.VIDEO:
                video = self.session.get(Video, target_id)
                if video is not None:
                    self.covers.generate_cover_prompts(video)
                    self.session.refresh(video)
                    result = self._cover_prompt_card(video, prefix="Video onaylandi. Simdi kapak promptlari hazir.")
                    result["approval_id"] = approval.id
                    result["callback_message"] = "Video onaylandi, kapak promptlari hazirlandi."
                    return result
            message = self._approval_result_message(target_type, target_id, ApprovalAction.APPROVE)
            return {"message": message, "approval_id": approval.id, "callback_message": "Onaylandi."}
        if action_name == "reject":
            approval = self.approvals.apply(target_type=target_type, target_id=target_id, action=ApprovalAction.REJECT)
            message = self._approval_result_message(target_type, target_id, ApprovalAction.REJECT)
            return {"message": message, "approval_id": approval.id, "callback_message": "Reddedildi."}
        if action_name == "regenerate":
            if target_type == ApprovalTarget.PROMPT:
                prompt = self.session.get(Prompt, target_id)
                if prompt is None:
                    return {"message": "Prompt bulunamadi.", "callback_message": "Prompt yok."}
                revised_prompt = self.editor.regenerate_prompt(prompt)
                result = self._prompt_approval_card(revised_prompt, prefix="Prompt yeniden uretildi.")
                result["callback_message"] = "Yeni prompt hazir."
                return result
            if target_type == ApprovalTarget.VIDEO:
                video = self.session.get(Video, target_id)
                if video is None:
                    return {"message": "Video bulunamadi.", "callback_message": "Video yok."}
                revised_video = self.editor.regenerate_video(video)
                result = self._video_approval_card(revised_video, prefix="Video yeniden uretim istegi olusturuldu.")
                result["callback_message"] = "Yeni video hazir."
                return result
        if action_name == "approvecover":
            if target_type != ApprovalTarget.VIDEO:
                return {"message": "Kapak prompt onayi sadece video icin kullanilir.", "callback_message": "Gecersiz."}
            video = self.session.get(Video, target_id)
            if video is None:
                return {"message": "Video bulunamadi.", "callback_message": "Video yok."}
            self.covers.approve_cover_prompts(video)
            self.session.refresh(video)
            result = self._cover_prompt_card(video, prefix="Kapak promptlari onaylandi.")
            result["callback_message"] = "Kapak promptlari onaylandi."
            return result
        if action_name == "generatecovers":
            if target_type != ApprovalTarget.VIDEO:
                return {"message": "Kapak gorsel uretimi sadece video icin kullanilir.", "callback_message": "Gecersiz."}
            video = self.session.get(Video, target_id)
            if video is None:
                return {"message": "Video bulunamadi.", "callback_message": "Video yok."}
            try:
                assets = self.covers.generate_cover_images(video)
            except Exception as exc:
                return {"message": f"Kapak gorselleri uretilemedi: {exc}", "callback_message": "Kapak uretilemedi."}
            result = self._cover_assets_message(video.id, assets, prefix="Kapak gorselleri uretildi.")
            result["callback_message"] = "Kapak gorselleri hazir."
            return result
        return {"message": "Bu buton islemi desteklenmiyor.", "callback_message": "Desteklenmiyor."}

    def _prompt_approval_card(self, prompt: Prompt, *, prefix: str) -> dict:
        hook = prompt.metadata_payload.get("hook") or "-"
        visual_style = prompt.metadata_payload.get("visual_style") or "-"
        return {
            "message": (
                f"{prefix}\n\n"
                f"Prompt ID: {prompt.id}\n"
                f"Versiyon: {prompt.version}\n"
                f"Durum: {prompt.status.value} ve onay bekliyor\n"
                f"Baslik: {prompt.title}\n"
                f"Ton: {prompt.tone}\n"
                f"Hook: {hook}\n"
                f"Gorsel stil: {visual_style}\n\n"
                "Sonraki adim: Onayla, reddet veya yeniden uret. Metin duzenleme icin /edit_prompt kullan."
            ),
            "prompt_id": prompt.id,
            "reply_markup": self._build_inline_keyboard(
                [
                    [("Onayla", f"approve:prompt:{prompt.id}"), ("Reddet", f"reject:prompt:{prompt.id}")],
                    [("Yeniden Uret", f"regenerate:prompt:{prompt.id}")],
                ]
            ),
        }

    def _video_approval_card(self, video: Video, *, prefix: str) -> dict:
        preview = video.preview_url or "yok"
        return {
            "message": (
                f"{prefix}\n\n"
                f"Video ID: {video.id}\n"
                f"Durum: {video.status.value} ve operator onayi bekliyor\n"
                f"Baslik: {video.title}\n"
                f"Provider: {video.provider_name}\n"
                f"Sure: {video.format_payload.get('total_duration_seconds', 20)} saniye toplam, {video.format_payload.get('segment_count', 2)}x{video.format_payload.get('segment_duration_seconds', 10)} saniye\n"
                f"Onizleme: {preview}\n\n"
                "Sonraki adim: Onayla, reddet veya yeniden uret. Video brief duzenlemek icin /edit_video kullan. Segmentler hazirsa /merge_video ile birlestir."
            ),
            "video_id": video.id,
            "reply_markup": self._build_inline_keyboard(
                [
                    [("Onayla", f"approve:video:{video.id}"), ("Reddet", f"reject:video:{video.id}")],
                    [("Yeniden Uret", f"regenerate:video:{video.id}")],
                ]
            ),
        }

    def _cover_prompt_card(self, video: Video, *, prefix: str) -> dict:
        covers_payload = (video.format_payload or {}).get("covers") or {}
        prompts = covers_payload.get("prompts") or {}
        lines = [f"{prefix}", "", f"Video ID: {video.id}", f"Prompt durumu: {covers_payload.get('prompt_status', 'draft')}"]
        for platform in [Platform.YOUTUBE.value, Platform.INSTAGRAM.value, Platform.TIKTOK.value, Platform.FACEBOOK.value]:
            item = prompts.get(platform) or {}
            if not item:
                continue
            lines.append(f"{platform}: {str(item.get('prompt', ''))[:140]}")
        lines.append("")
        lines.append("Sonraki adim: promptlari onayla, sonra kapak gorsellerini uret.")
        return {
            "message": "\n".join(lines),
            "video_id": video.id,
            "reply_markup": self._build_inline_keyboard(
                [
                    [("Promptlari Onayla", f"approvecover:video:{video.id}")],
                    [("Kapaklari Uret", f"generatecovers:video:{video.id}")],
                ]
            ),
        }

    def _cover_assets_message(self, video_id: int, assets: dict, *, prefix: str) -> dict:
        first_photo_url = None
        lines = [prefix, "", f"Video ID: {video_id}"]
        for platform, asset in assets.items():
            image_url = asset.get("image_url")
            if image_url and not first_photo_url:
                first_photo_url = image_url
            lines.append(
                f"- {platform}: {'hazir' if image_url else 'basarisiz'} | upload_support: {'evet' if asset.get('upload_supported') else 'hayir'} | url: {image_url or 'yok'}"
            )
        lines.append("")
        lines.append("Yayin sonrasi raporda kapak uygulama durumu da doner.")
        result = {"message": "\n".join(lines), "video_id": video_id}
        if first_photo_url:
            result["photo_url"] = first_photo_url
        return result

    @staticmethod
    def _build_inline_keyboard(rows: list[list[tuple[str, str]]]) -> dict:
        return {
            "inline_keyboard": [
                [{"text": text, "callback_data": callback_data} for text, callback_data in row]
                for row in rows
            ]
        }

    def _approval_result_message(self, target_type: ApprovalTarget, target_id: int, action: ApprovalAction) -> str:
        if target_type == ApprovalTarget.PROMPT:
            prompt = self.session.get(Prompt, target_id)
            if prompt is None:
                return "Prompt bulunamadi."
            suffix = "/video <prompt_id> ile video asamasina gecebilirsin." if action == ApprovalAction.APPROVE else "Yeni varyasyon icin /regenerate_prompt kullanabilirsin."
            return f"Prompt {prompt.id} icin islem tamamlandi. Yeni durum: {prompt.status.value}. {suffix}"
        if target_type == ApprovalTarget.VIDEO:
            video = self.session.get(Video, target_id)
            if video is None:
                return "Video bulunamadi."
            suffix = "/cover_prompts <video_id> ile kapak promptlarini gorebilir, sonra /generate_covers ile gorsel uretebilirsin." if action == ApprovalAction.APPROVE else "Yeni varyasyon icin /regenerate_video kullanabilirsin."
            return f"Video {video.id} icin islem tamamlandi. Yeni durum: {video.status.value}. {suffix}"
        return f"{target_type.value} {target_id} icin islem tamamlandi."

    def _build_prompt_history_message(self, prompt: Prompt) -> str:
        prompts = self.session.query(Prompt).filter(Prompt.niche_id == prompt.niche_id).all()
        related_prompts = self._connected_prompt_chain(prompts, prompt.id)
        edit_request_ids = [item.metadata_payload.get("edit_request_id") for item in related_prompts if item.metadata_payload.get("edit_request_id")]
        edit_requests = self._edit_request_lookup(edit_request_ids)

        lines = [f"Prompt gecmisi: niche {prompt.niche_id} icinde {len(related_prompts)} kayit bulundu."]
        for item in sorted(related_prompts, key=lambda current: (current.version, current.created_at, current.id)):
            marker = "simdiki" if item.id == prompt.id else "gecmis"
            relation = self._prompt_relation_label(item)
            instruction = self._edit_instruction_text(item.metadata_payload.get("edit_request_id"), edit_requests)
            lines.append(
                f"- Prompt {item.id} | v{item.version} | {item.status.value} | {relation} | {marker} | {item.title}{instruction}"
            )
        return "\n".join(lines)

    def _build_video_history_message(self, video: Video) -> str:
        videos = self.session.query(Video).filter(Video.prompt_id == video.prompt_id).all()
        related_videos = self._connected_video_chain(videos, video.id)
        edit_request_ids = [item.format_payload.get("edit_request_id") for item in related_videos if item.format_payload.get("edit_request_id")]
        edit_requests = self._edit_request_lookup(edit_request_ids)

        lines = [f"Video gecmisi: prompt {video.prompt_id} icinde {len(related_videos)} kayit bulundu."]
        for item in sorted(related_videos, key=lambda current: (current.created_at, current.id)):
            marker = "simdiki" if item.id == video.id else "gecmis"
            relation = self._video_relation_label(item)
            instruction = self._edit_instruction_text(item.format_payload.get("edit_request_id"), edit_requests)
            lines.append(
                f"- Video {item.id} | {item.status.value} | {relation} | {marker} | {item.title}{instruction}"
            )
        return "\n".join(lines)

    @staticmethod
    def _prompt_relation_label(prompt: Prompt) -> str:
        if prompt.metadata_payload.get("edited_from_prompt_id"):
            return f"edit <- {prompt.metadata_payload['edited_from_prompt_id']}"
        if prompt.metadata_payload.get("regenerated_from_prompt_id"):
            return f"regenerate <- {prompt.metadata_payload['regenerated_from_prompt_id']}"
        return "initial"

    @staticmethod
    def _video_relation_label(video: Video) -> str:
        if video.format_payload.get("edited_from_video_id"):
            return f"edit <- {video.format_payload['edited_from_video_id']}"
        if video.format_payload.get("regenerated_from_video_id"):
            return f"regenerate <- {video.format_payload['regenerated_from_video_id']}"
        return "initial"

    @staticmethod
    def _edit_instruction_text(edit_request_id: int | None, edit_requests: dict[int, EditRequest]) -> str:
        if not edit_request_id:
            return ""
        edit_request = edit_requests.get(edit_request_id)
        if edit_request is None:
            return ""
        return f" | talimat: {edit_request.instruction}"

    def _edit_request_lookup(self, edit_request_ids: list[int]) -> dict[int, EditRequest]:
        if not edit_request_ids:
            return {}
        requests = self.session.query(EditRequest).filter(EditRequest.id.in_(edit_request_ids)).all()
        return {item.id: item for item in requests}

    def _connected_prompt_chain(self, prompts: list[Prompt], selected_id: int) -> list[Prompt]:
        return self._connected_component(
            items=prompts,
            selected_id=selected_id,
            item_id=lambda item: item.id,
            parent_ids=lambda item: [
                parent_id
                for parent_id in [item.metadata_payload.get("edited_from_prompt_id"), item.metadata_payload.get("regenerated_from_prompt_id")]
                if parent_id is not None
            ],
        )

    def _connected_video_chain(self, videos: list[Video], selected_id: int) -> list[Video]:
        return self._connected_component(
            items=videos,
            selected_id=selected_id,
            item_id=lambda item: item.id,
            parent_ids=lambda item: [
                parent_id
                for parent_id in [item.format_payload.get("edited_from_video_id"), item.format_payload.get("regenerated_from_video_id")]
                if parent_id is not None
            ],
        )

    @staticmethod
    def _connected_component(items: list, selected_id: int, item_id, parent_ids) -> list:
        items_by_id = {item_id(item): item for item in items}
        neighbors: dict[int, set[int]] = {item_id(item): set() for item in items}
        for item in items:
            current_id = item_id(item)
            for parent_id in parent_ids(item):
                if parent_id in neighbors:
                    neighbors[current_id].add(parent_id)
                    neighbors[parent_id].add(current_id)

        visited: set[int] = set()
        stack = [selected_id]
        while stack:
            current_id = stack.pop()
            if current_id in visited or current_id not in items_by_id:
                continue
            visited.add(current_id)
            stack.extend(neighbors.get(current_id, set()) - visited)
        return [items_by_id[current_id] for current_id in visited]

    def _approval_command(self, text: str, action: ApprovalAction) -> dict:
        parts = text.split(maxsplit=2)
        if len(parts) != 3 or not parts[2].isdigit():
            raise ValueError(f"Kullanim: /{action.value} <niche|prompt|video> <id>")
        try:
            target_type = ApprovalTarget(parts[1])
        except ValueError as exc:
            raise ValueError("Gecersiz hedef tipi. Yalnizca niche, prompt veya video kullanin.") from exc
        approval = self.approvals.apply(target_type=target_type, target_id=int(parts[2]), action=action)
        if action == ApprovalAction.APPROVE and target_type == ApprovalTarget.VIDEO:
            video = self.session.get(Video, int(parts[2]))
            if video is not None:
                self.covers.generate_cover_prompts(video)
                self.session.refresh(video)
                result = self._cover_prompt_card(video, prefix="Video onaylandi. Simdi kapak promptlari hazir.")
                result["approval_id"] = approval.id
                return result
        return {"message": "Onay kaydedildi." if action == ApprovalAction.APPROVE else "Red kaydedildi.", "approval_id": approval.id}

    @staticmethod
    def _parse_single_int_argument(text: str, *, command: str) -> int:
        parts = text.split(maxsplit=1)
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError(f"Kullanim: {command} <id>")
        return int(parts[1])

    @staticmethod
    def _parse_id_and_instruction(text: str, *, command: str) -> tuple[int, str]:
        parts = text.split(maxsplit=2)
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].strip():
            raise ValueError(f"Kullanim: {command} <id> <talimat>")
        return int(parts[1]), parts[2].strip()

    @staticmethod
    def _help_message(display_name: str, project_name: str) -> str:
        return (
            f"Hos geldiniz {display_name}. Proje: {project_name}\n\n"
            "Komut Rehberi:\n\n"
            "/help\nBotta kullanabileceginiz tum komutlari ve amaclarini gosterir.\n\n"
            "/scan\nGunluk web tabanli trend niche taramasini calistirir.\n\n"
            "/prompts <niche_id>\nSecilen niche icin 10 adet icerik promptu uretir.\n\n"
            "/video <prompt_id>\nSecilen prompttan video uretim istegi baslatir.\n\n"
            "/approve <niche|prompt|video> <id>\nSecilen kaydi onaylar ve pipeline'da bir sonraki asamaya gecmesini saglar.\n\n"
            "/reject <niche|prompt|video> <id>\nSecilen kaydi reddeder.\n\n"
            "/status\nNiche, prompt ve video sayilarinin genel ozetini verir.\n\n"
            "/accounts\nBagli sosyal medya hesaplarini listeler.\n\n"
            "/history <prompt|video> <id>\n"
            "Secilen prompt veya videonun revizyon gecmisini listeler.\n\n"
            "/connect <platform> <gorunen_ad> [external_account_id]\n"
            "Secilen platform icin OAuth baglanti linki uretir. Platform: youtube, instagram, facebook, tiktok.\n\n"
            "/validate_account <account_id>\nBagli hesabin token ve gerekli metadata durumunu dogrular.\n\n"
            "/publish_check <video_id> <account_id>\n"
            "Belirli video ile belirli hesabin yayin icin hazir olup olmadigini kontrol eder.\n\n"
            "/publish <video_id> <account_id> [caption]\n"
            "Belirli videoyu secilen hesaba gondermeyi dener. Oncesinde /publish_check kullanilmasi tavsiye edilir.\n\n"
            "/edit_prompt <prompt_id> <duzenleme_talimati>\n"
            "Begeniye uymayan prompt icin revize bir prompt uretir.\n\n"
            "/regenerate_prompt <prompt_id>\n"
            "Secilen prompt icin alternatif yeni bir prompt uretir.\n\n"
            "/edit_video <video_id> <duzenleme_talimati>\n"
            "Begeniye uymayan video icin yeni bir revize video uretim istegi baslatir.\n\n"
            "/regenerate_video <video_id>\n"
            "Secilen video icin yeni bir video uretim istegi baslatir.\n\n"
            "/merge_video <video_id>\n"
            "Iki adet 10 saniyelik segmenti tek dosyada birlestirmeyi dener.\n\n"
            "/cover_prompts <video_id>\n"
            "Video onayi sonrasi platform bazli kapak promptlarini uretir veya listeler.\n\n"
            "/approve_cover_prompt <video_id>\n"
            "Kapak promptlarini onaylar.\n\n"
            "/generate_covers <video_id>\n"
            "Onayli kapak promptlari ile platform bazli kapak gorsellerini uretir.\n\n"
            "Not: Revize veya yeniden uretilen prompt/video mesajlarinda inline butonlarla hizli onay, red ve yeniden uretim yapabilirsiniz."
        )

    def _sync_user_from_payload(self, payload: TelegramWebhookPayload, user: User) -> User:
        message = payload.message or {}
        from_user = message.get("from") or {}
        chat = message.get("chat") or {}
        telegram_user_id = from_user.get("id")
        telegram_chat_id = chat.get("id")
        if telegram_user_id:
            user.telegram_user_id = telegram_user_id
        if telegram_chat_id:
            user.telegram_chat_id = telegram_chat_id
        first_name = from_user.get("first_name")
        username = from_user.get("username")
        if username:
            user.display_name = f"@{username}"
        elif first_name:
            user.display_name = first_name
        self.session.commit()
        self.session.refresh(user)
        return user

    @staticmethod
    def _extract_text(payload: TelegramWebhookPayload) -> str | None:
        if payload.message:
            return payload.message.get("text")
        if payload.callback_query:
            return payload.callback_query.get("data")
        return None

    @staticmethod
    def _extract_chat_id(payload: TelegramWebhookPayload) -> int | None:
        if payload.message:
            chat = payload.message.get("chat") or {}
            return chat.get("id")
        if payload.callback_query:
            callback_message = payload.callback_query.get("message") or {}
            chat = callback_message.get("chat") or {}
            return chat.get("id")
        return None
