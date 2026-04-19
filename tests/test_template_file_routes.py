from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_upload_template_pdf():
    pdf_content = b"%PDF-1.4 test pdf content"

    files = {
        "file": ("sample_test.pdf", pdf_content, "application/pdf")
    }

    data = {
        "directory": "src/inputs"
    }

    response = client.post(
        "/templates/upload",
        files=files,
        data=data
    )

    assert response.status_code == 200

    response_data = response.json()

    assert "filename" in response_data
    assert "pdf_path" in response_data
    assert response_data["filename"].endswith(".pdf")


def test_preview_template_pdf():
    response = client.get(
        "/templates/preview",
        params={"path": "src/inputs/file.pdf"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    
def test_upload_non_pdf_should_fail():
    files = {
        "file": ("sample.txt", b"not a pdf", "text/plain")
    }

    response = client.post(
        "/templates/upload",
        files=files,
        data={"directory": "src/inputs"}
    )

    assert response.status_code == 400


def test_preview_missing_file_should_fail():
    response = client.get(
        "/templates/preview",
        params={"path": "src/inputs/does_not_exist.pdf"}
    )

    assert response.status_code == 404


def test_preview_outside_project_should_fail():
    response = client.get(
        "/templates/preview",
        params={"path": "/etc/passwd"}
    )

    assert response.status_code == 400
