from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_auth_token: str
    openai_api_key: str
    twilio_account_sid: str | None
    twilio_auth_token: str | None
    twilio_phone_number: str | None
    donation_url: str
    monitor_interval_minutes: int
    monitor_match_limit: int

    @property
    def twilio_enabled(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_phone_number)


def load_settings() -> Settings:
    api_auth_token = os.getenv("API_AUTH_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not api_auth_token:
        raise RuntimeError("Missing required environment variable: API_AUTH_TOKEN")
    if not openai_api_key:
        raise RuntimeError("Missing required environment variable: OPENAI_API_KEY")

    return Settings(
        api_auth_token=api_auth_token,
        openai_api_key=openai_api_key,
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN"),
        twilio_phone_number=os.getenv("TWILIO_PHONE_NUMBER"),
        donation_url=os.getenv("DONATION_URL", "https://buy.stripe.com/"),
        monitor_interval_minutes=max(1, int(os.getenv("MONITOR_INTERVAL_MINUTES", "60"))),
        monitor_match_limit=max(1, int(os.getenv("MONITOR_MATCH_LIMIT", "3"))),
    )
