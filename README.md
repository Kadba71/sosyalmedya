# Telegram AI Video Automation

Telegram uzerinden onayli ilerleyen, 3 agent mantiginda tasarlanmis, Railway uzerinde yayinlanacak ve agir AI katmani ayri sunucuda kosacak bir otomasyon backend'i.

## Kapsam

- Gunluk trend niche tarama akisi
- Secilen niche icin 10 prompt uretim akisi
- Secilen prompt icin video uretim pipeline iskeleti
- Video uretimi 9:16 short formatinda toplam 20 saniyedir
- Uretim 2 adet 10 saniyelik segment halinde yapilir
- Segmentler sonradan ffmpeg ile tek videoda birlestirilebilir
- Video onayi sonrasi platform bazli kapak promptlari otomatik uretilebilir
- Onayli kapak promptlarindan Flux ile kapak gorselleri uretilir
- Publish sonucunda platform bazli kapak uygulama raporu doner
- Telegram ile onay, red, yeniden uretim ve duzenleme akisi
- YouTube, Instagram, TikTok, Facebook hesap baglama ve yayinlama iskeleti
- Manuel hesap secimi ve publish profile birlikte desteklenir
- Prompt ve video asset'leri 24 saat tutulur, sonra cleanup ile silinir

## Mimari Ozeti

- `FastAPI`: admin API, Telegram webhook ve OAuth callback iskeleti
- `SQLAlchemy`: kalici veritabani modeli
- `APScheduler`: gunluk tarama ve retention cleanup job'lari
- `ProviderRegistry`: trend, prompt, video icin bos adapter katmani
- `PublisherRegistry`: sosyal platform publish adapter katmani

## LLM Katmani

Prompt ve arastirma icin uygulama artik OpenAI-compatible bir LLM endpoint'ine baglanir.

- Varsayilan endpoint: `https://api.piapi.ai/v1`
- Arastirma modeli: `gpt-4o`
- Prompt modeli: `gpt-4o`
- Fallback modeli: `gpt-4o-mini`
- Coding agent servisi: `Aider`

Bu katman lokal gelistirme icin zorunlu degildir; Railway veya baska bir cloud ortamindan PiAPI GPT-4o endpoint'ine dogrudan baglanabilir.

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env
uvicorn app.main:app --reload
```

## Sunucuda AI Stack

Sunucuda calisacak 2 servislik stack:

```bash
docker compose up -d
```

Servisler:

- `aider`: repo uzerinde self-hosted coding agent olarak calisir.

Dosyalar:

- `docker-compose.yml`
- `docker/aider/entrypoint.sh`
- `docker/aider/.aider.conf.yml`
- `docker/aider/.aider.model.settings.yml`

Notlar:

- Bu stack sunucu odaklidir.
- Backend arastirma/prompt provider'lari PiAPI GPT-4o gibi OpenAI-compatible bir endpoint'e dogrudan baglanir.

## Web Tabanli Genis Piyasa Arastirmasi

Trend tarama artik yalnizca model prompt'una dayanmiyor. Sistem once kamuya acik web sinyallerini topluyor, sonra LLM bu sinyalleri niche seviyesinde yorumluyor.

Kaynaklar:

- `Google Trends TR RSS`
- `TikTok Creative Center` populer hashtag sinyalleri
- `YouTube Official Blog` trend ve creator sinyalleri
- `Instagram Blog` reels, stories, notes ve product/topic sinyalleri
- `Facebook Business News` trend ve sektor sinyalleri

Ilgili kod:

- `app/services/web_research_service.py`
- `app/providers/trend/llm.py`

Calisma mantigi:

1. Web kaynaklarindan baslik ve ozet sinyalleri toplanir.
2. Bu sinyaller tek JSON blok halinde LLM arastirma modeline verilir.
3. Model bunlardan daginik trend kelimeleri degil, secilebilir niche listesi uretir.

Sinirlar:

- YouTube, TikTok, Instagram ve Facebook tarafinda herkese acik resmi `tum trend nisleri getir` endpoint'i bulunmaz.
- Bu nedenle sistem resmi public sayfalar ve public trend kaynaklari uzerinden sinyal toplar.
- Daha sonra istenirse resmi API anahtarlari ile bu katman genisletilebilir.

## Benchmark ile Model Secimi

Arastirma ve prompt modeli sabit secilmek zorunda degil. Sistem artik iki modeli benchmark edip birincil modeli kaydedebilir.

- `POST /api/admin/benchmark` with `{"scope":"trend","market":"tr-TR","sample_count":2}`
- `POST /api/admin/benchmark` with `{"scope":"prompt","market":"tr-TR","sample_count":2}`

Benchmark sonucu `ProviderConfig` icine kaydedilir ve aktifse provider secimi otomatik olarak bu sonuca gore yapilir.

Varsayilan mantik:

- Trend/arastirma icin `gpt-4o`
- Prompt uretimi icin `gpt-4o`
- Benchmark sonucu daha iyi cikarsa secim otomatik degisir

## Aider Gorev Kuyrugu

Aider artik backend workflow'una kuyruk mantigi ile baglanabilir.

- `POST /api/admin/aider/tasks` ile gorev eklenir
- `POST /api/internal/aider/next` worker tarafinda sıradaki gorevi claim eder
- `POST /api/internal/aider/{task_id}` worker sonucunu geri yazar

Bu tasarimla Aider servisi backend'den bagimsiz ama kontrollu sekilde calisir. Uygun oldugunda bir gorevi alip `aider --message` ile uygular ve sonucu kaydeder.

## Prod Topolojisi

Pratik uretim topolojisi hibrittir:

- `Railway`: public backend, Telegram webhook, admin API
- `Harici AI Servisi`: PiAPI GPT-4o veya baska bir OpenAI-compatible LLM, benchmark, Aider worker

Bu tercih pratikte daha saglamdir; backend dogrudan harici LLM endpoint'ine baglanir.

Yine de tam sunucu stack dosyalari korunuyor. Isterseniz backend'i de sonradan bu stack'e alabilirsiniz.

Sunucu odakli tam stack:

- `postgres`: kalici veritabani
- `backend`: FastAPI uygulamasi
- `aider`: kuyruk tabanli coding agent worker
- `caddy`: reverse proxy + TLS sonlandirma

Prod dosyalari:

- `docker-compose.prod.yml`
- `deploy/.env.prod.example`
- `deploy/Caddyfile`

Railway dosyalari:

- `railway.toml`
- `railway.json`
- `deploy/railway.env.example`

Calistirma:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Bu topolojiyle yayin Railway uzerinden yapilir. Backend tarafinda yapmaniz gereken temel ayar `LLM_API_BASE` degiskenini PiAPI gibi OpenAI-compatible bir servise vermektir.

## Temel API Akisi

1. `POST /api/admin/bootstrap`
2. `POST /api/admin/scan`
3. `POST /api/admin/prompts` with `{"niche_id": 1}`
4. `POST /api/admin/video` with `{"prompt_id": 1}`
5. `POST /api/admin/approve` with `{"target_type": "video", "target_id": 1, "action": "approve"}`
6. `POST /api/admin/videos/{video_id}/cover-prompts`
7. `POST /api/admin/videos/{video_id}/cover-prompts/approve`
8. `POST /api/admin/videos/{video_id}/covers/generate`
9. `POST /api/admin/accounts` ile hesap bagla
10. `POST /api/admin/publish` ile manuel hesaplar veya publish profile uzerinden yayin kaydi olustur

## Telegram Komutlari

- `/start`
- `/help`
- `/scan`
- `/prompts <niche_id>`
- `/video <prompt_id>`
- `/approve <niche|prompt|video> <id>`
- `/reject <niche|prompt|video> <id>`
- `/status`
- `/accounts`
- `/connect <platform> <gorunen_ad> [external_account_id]`
- `/validate_account <account_id>`
- `/cover_prompts <video_id>`
- `/approve_cover_prompt <video_id>`
- `/generate_covers <video_id>`

## Retention Kurali

- Prompt icerikleri 24 saat sonra silinir veya anonimlestirilir.
- Video dosyalari ve preview referanslari 24 saat sonra temizlenir.
- Yayin kayitlari, audit izleri ve operasyonel metadata korunur.

## Railway

Bu proje Railway'de backend olarak calisir. Video dosyalari icin Railway volume yerine harici object storage kullanmaniz daha saglam olur; mevcut retention mantigi yine 24 saat sonra prompt ve video kayitlarini temizler. `railway.toml` ve `railway.json` temel baslatma komutlarini icerir.

Railway webhook kaydi icin gerekli alan:

- `PUBLIC_BASE_URL=https://your-app.up.railway.app`

Webhook kayit endpoint'i:

- `POST /api/admin/telegram/webhook/sync`

Webhook durum ozeti:

- `GET /api/admin/telegram/diagnostics`

Telegram baglama akisi:

1. `POST /api/admin/telegram/webhook/sync` ile webhook Railway domainine baglanir.
2. Telegram'da bot'a `/connect youtube KanalAdi` veya `/connect instagram MarkaAdi ig_user_id` gonderilir.
3. Bot size resmi OAuth baglanti linkini mesaj olarak gonderir.
4. OAuth tamamlaninca hesap otomatik kaydolur.
5. `/accounts` ile bagli hesaplari listeleyin.
6. `/validate_account <account_id>` ile token ve metadata dogrulamasini yapin.

## Video Provider

Video uretimi icin Kling 3.0, PiAPI uzerinden entegre edildi. Gerekli env alanlari:

```bash
VIDEO_PROVIDER=kling
PIAPI_BASE_URL=https://api.piapi.ai
PIAPI_API_KEY=your_piapi_key
PIAPI_SERVICE_MODE=public
KLING_MODEL=kling
KLING_VERSION=3.0
KLING_DEFAULT_MODE=std
KLING_DEFAULT_DURATION=5
KLING_DEFAULT_ASPECT_RATIO=9:16
KLING_ENABLE_AUDIO=false
```

Bu entegrasyon `create task` ve `get task` akisini kullanir. Video talebi olustugunda sistem tek parca video yerine 2 adet 10 saniyelik segment uretir.

Akis:

1. Prompt tarafi her zaman `9:16` short formatinda ve toplam `20 saniye` olacak sekilde uretilir.
2. Video isteme asamasinda bu brief 2 adet `10 saniyelik` segmente bolunur.
3. Ikinci segment brief'i, birinci segmentin son karesinden devam edecek sekilde continuity talimati alir.
4. Her iki segment hazir oldugunda merge adimi ile tek dosyada birlestirilebilir.

## Kapak Gorsel Akisi

Video onayindan sonra sistem kapak tarafini ayri bir asama olarak yonetir.

Akis:

1. Video onaylandiginda YouTube, Instagram, TikTok ve Facebook icin kapak promptlari uretilir.
2. Operator kapak promptlarini onaylar.
3. PiAPI Flux ile platforma uygun oranlarda kapak gorselleri uretilir.
4. Publish sirasinda desteklenen platformlarda kapak uygulanir ve sonuc rapora yazilir.

Boyutlar:

- YouTube: `1280x720`
- Instagram Reel cover: `1080x1920`
- TikTok cover: `1080x1920`
- Facebook Reel/video cover: `1080x1920`

Mevcut otomasyon destegi:

- YouTube: custom thumbnail upload denenir
- Instagram: kapak URL'si rapora yazilir, otomatik uygulama bu API akista bagli degil
- TikTok: kapak URL'si rapora yazilir, creator-side cover secimi gerekir
- Facebook: kapak URL'si rapora yazilir, otomatik uygulama bu akista bagli degil

Merge secenekleri:

- `POST /api/admin/videos/{video_id}/merge`
- Telegram: `/merge_video <video_id>`

Merge islemi icin sistem `ffmpeg` kullanir. Birlesik dosya local `storage/videos/.../merged.mp4` altina yazilir.

## Arastirma ve Prompt Provider

Arastirma ve prompt uretimi artik dummy degil; OpenAI-compatible chat completions endpoint'i uzerinden calisir.

- `app/providers/trend/llm.py`
- `app/providers/prompt/llm.py`
- `app/providers/llm_client.py`

Varsayilan tercih:

- Trend/arastirma icin `gpt-4o`
- Prompt uretimi icin `gpt-4o`
- Hata durumunda `gpt-4o-mini` fallback

## Gercek Provider Entegrasyonlari

Sosyal publish katmanlari halen bos adapter mantigi ile calisir. Gercek servisler eklenecek noktalar:

- `app/providers/trend/`
- `app/providers/prompt/`
- `app/publishers/`

## Gercek Publish Adapter Gereksinimleri

Publisher katmani artik resmi API isteklerini gonderir. Her platform icin hesap metadata veya override alanlarinin dogru verilmesi gerekir.

YouTube:

- Gereken scope: YouTube upload yetkisi
- Video kaynagi: `video.preview_url` veya publish override icinde `video_url`
- Opsiyonel override: `title`, `description`, `privacy_status`, `category_id`, `tags`, `made_for_kids`

Instagram Reels:

- Gereken hesap verisi: `instagram_user_id` metadata icinde veya override icinde
- Video kaynagi kamuya acik URL olmali
- Opsiyonel override: `caption`, `share_to_feed`

Facebook:

- Gereken hesap verisi: `facebook_page_id` metadata icinde veya override icinde
- Video kaynagi kamuya acik URL olmali
- Opsiyonel override: `title`, `description`

TikTok:

- Gereken scope: content posting yetkisi
- Video kaynagi kamuya acik URL olmali
- Opsiyonel override: `title`, `description`, `privacy_level`, `disable_duet`, `disable_comment`, `disable_stitch`

Ham research sinyallerini gormek icin:

- `GET /api/admin/research/signals?market=tr-TR`
