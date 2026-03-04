from pathlib import Path

from privacy import format_display_phone, normalize_phone

REPO_URL = "https://github.com/grandSpecial/tri2vec"


def render_landing_page(static_dir: Path, phone: str | None) -> str:
    template_path = static_dir / "landing.html"
    html = template_path.read_text(encoding="utf-8")
    sms_target = normalize_phone(phone or "") or ""
    sms_href = f"sms:{sms_target}" if sms_target else "#"
    return (
        html.replace("__DISPLAY_PHONE__", format_display_phone(phone))
        .replace("__SMS_HREF__", sms_href)
    )


def render_about_page(static_dir: Path, phone: str | None) -> str:
    template_path = static_dir / "about.html"
    html = template_path.read_text(encoding="utf-8")
    return (
        html.replace("__DISPLAY_PHONE__", format_display_phone(phone))
        .replace("__REPO_URL__", REPO_URL)
    )
