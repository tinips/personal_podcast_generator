"""Generate the spoken sample.mp3 demo artifact."""
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from .services.tts_service import _is_usable_mp3

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = BACKEND_DIR / "audio"
ROOT_SAMPLE_PATH = REPO_ROOT / "sample.mp3"
BACKEND_SAMPLE_PATH = AUDIO_DIR / "sample.mp3"

SAMPLE_SCRIPT = (
    "Welcome to your personalized editorial briefing. "
    "Today, we are tracking three stories that show how fast technology, "
    "climate innovation, and science are reshaping daily life. "
    "First, artificial intelligence systems are becoming better at complex "
    "reasoning, which could make research tools and personal assistants more "
    "useful. Next, climate technology investment continues to grow, pushing "
    "clean energy and carbon capture closer to mainstream use. Finally, new "
    "medical breakthroughs show how gene editing may change treatment for "
    "serious inherited diseases. The thread connecting these stories is simple: "
    "big technical shifts matter most when they become practical for people."
)


def _load_local_env() -> None:
    load_dotenv(BACKEND_DIR / ".env")
    load_dotenv(REPO_ROOT / ".env")


def _copy_root_sample_to_backend() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT_SAMPLE_PATH, BACKEND_SAMPLE_PATH)


def _generate_with_openai() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required to regenerate sample.mp3. "
            "The committed root sample.mp3 is a demo artifact."
        )

    client = OpenAI(api_key=api_key)
    last_error: Exception | None = None

    for model in ("gpt-4o-mini-tts", "tts-1"):
        try:
            response = client.audio.speech.with_streaming_response.create(
                model=model,
                voice="alloy",
                input=SAMPLE_SCRIPT,
            )
            with response as stream:
                stream.stream_to_file(ROOT_SAMPLE_PATH)
            if _is_usable_mp3(ROOT_SAMPLE_PATH):
                return model
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Could not generate spoken sample.mp3: {last_error}")


def main() -> None:
    _load_local_env()

    if _is_usable_mp3(ROOT_SAMPLE_PATH):
        _copy_root_sample_to_backend()
        print(f"Existing spoken sample is usable: {ROOT_SAMPLE_PATH}")
        print(f"Copied demo sample to: {BACKEND_SAMPLE_PATH}")
        return

    model = _generate_with_openai()
    _copy_root_sample_to_backend()
    print(f"Generated spoken sample with {model}: {ROOT_SAMPLE_PATH}")
    print(f"Copied demo sample to: {BACKEND_SAMPLE_PATH}")


if __name__ == "__main__":
    main()
