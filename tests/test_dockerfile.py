from pathlib import Path


def test_dockerfile_exists():
    project_root = Path(__file__).resolve().parents[1]
    dockerfile = project_root / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile is missing; required for Docker image build"


def test_docker_image_defaults_to_production_api_and_media():
    root = Path(__file__).resolve().parents[1]
    text = (root / "Dockerfile").read_text(encoding="utf-8")
    assert "APTEKA_BASE_URL=https://api.apteka.md" in text
    assert "APTEKA_MEDIA_BASE_URL=https://api.apteka.md" in text
    assert "https://stage.apteka.md" not in text


def test_docker_context_excludes_local_environment_and_development_artifacts():
    root = Path(__file__).resolve().parents[1]
    ignore = root / ".dockerignore"
    assert ignore.exists()
    patterns = set(ignore.read_text(encoding="utf-8").splitlines())
    assert {".env", ".env.*", ".git", ".venv", "node_modules", "tests/.tmp"} <= patterns
