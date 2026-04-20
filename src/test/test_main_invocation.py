from pathlib import Path


def test_main_uses_static_fill_call():
    """Guard against reintroducing constructor/call mismatch for Fill."""
    main_path = Path(__file__).resolve().parents[1] / "main.py"
    content = main_path.read_text(encoding="utf-8")

    assert "Fill.fill_form(" in content
    assert "Fill(user_input=user_input).fill_form(" not in content
