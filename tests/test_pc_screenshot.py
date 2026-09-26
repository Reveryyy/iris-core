from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.tools.pc_screenshot import ScreenshotTool


def test_screenshot_accepts_dynamic_output_path(tmp_path, monkeypatch) -> None:
    target = tmp_path / "captures" / "desktop.png"

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=True: Image.new("RGB", (2, 2)),
    )

    result = ScreenshotTool().execute(
        {
            "output_path": str(target),
        }
    )

    assert result.success is True
    assert target.exists()
    assert result.output["path"] == str(target.resolve())
    assert result.output["format"] == "png"


def test_screenshot_definition_allows_optional_output_path() -> None:
    definition = ScreenshotTool().definition

    assert definition.name == "screenshot"
    assert "output_path" in definition.input_schema["properties"]
    assert definition.input_schema.get("required", []) == []
