from pathlib import Path


def test_docker_workflow_exists():
    project_root = Path(__file__).resolve().parents[1]
    workflow = project_root / ".github" / "workflows" / "docker-image.yml"
    assert workflow.exists(), "Docker build workflow is missing"


def test_docker_workflow_pushes_to_topf3_apteka_repo():
    project_root = Path(__file__).resolve().parents[1]
    workflow_text = (project_root / ".github" / "workflows" / "docker-image.yml").read_text(
        encoding="utf-8-sig"
    )

    assert "IMAGE_REPOSITORY: topf3/apteka-mcp" in workflow_text
    assert "${{ env.IMAGE_REPOSITORY }}:latest" in workflow_text
    assert "${{ env.IMAGE_REPOSITORY }}:${{ github.sha }}" in workflow_text
    assert "${{ secrets.DOCKERHUB_USERNAME }}/${{ env.IMAGE_NAME }}" not in workflow_text


def test_workflow_verifies_published_image_defaults_without_environment_override():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github/workflows/docker-image.yml").read_text(encoding="utf-8-sig")
    step = text.split("- name: Verify production image configuration", 1)
    assert len(step) == 2
    verification = step[1]
    assert "docker run --rm" in verification
    assert "${{ env.IMAGE_REPOSITORY }}:${{ github.sha }}" in verification
    assert "get_apteka_base_url() == 'https://api.apteka.md'" in verification
    assert "get_apteka_media_base_url() == 'https://api.apteka.md'" in verification
    assert "--env" not in verification
