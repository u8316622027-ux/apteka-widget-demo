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
