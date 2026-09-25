from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.tools.pc_screenshot import ScreenshotTool
from app.tools.permissions import Permission


class FakeImage:
    def __init__(self) -> None:
        self.save_calls: list[
            tuple[Path, str]
        ] = []

    def save(
        self,
        path,
        format=None,
    ) -> None:
        resolved_path = Path(path)

        self.save_calls.append(
            (
                resolved_path,
                format,
            )
        )

        resolved_path.write_bytes(
            b"fake png data"
        )


def test_screenshot_definition_requires_gui_and_write_permissions(
    tmp_path,
):
    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    definition = tool.definition

    assert definition.name == "screenshot"

    assert definition.risk_level == "medium"

    assert Permission.GUI.value in (
        definition.permissions
    )

    assert Permission.WRITE.value in (
        definition.permissions
    )

    assert definition.input_schema[
        "properties"
    ] == {}

    assert definition.input_schema[
        "additionalProperties"
    ] is False


def test_screenshot_rejects_arguments(
    tmp_path,
):
    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute(
        {
            "unexpected": True,
        }
    )

    assert result.success is False
    assert result.error is not None

    assert "non accetta argomenti" in (
        result.error.lower()
    )


def test_screenshot_accepts_empty_arguments(
    tmp_path,
    monkeypatch,
):
    fake_image = FakeImage()

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: fake_image,
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is True
    assert result.output is not None

    screenshot_path = Path(
        result.output[
            "path"
        ]
    )

    assert screenshot_path.exists()
    assert screenshot_path.is_file()

    assert screenshot_path.parent == (
        tmp_path / "screenshots"
    )

    assert screenshot_path.suffix == ".png"

    assert screenshot_path.name.startswith(
        "iris_"
    )

    assert result.output[
        "format"
    ] == "png"

    assert result.output[
        "bytes"
    ] == len(
        b"fake png data"
    )

    assert fake_image.save_calls == [
        (
            screenshot_path,
            "PNG",
        )
    ]


def test_screenshot_calls_imagegrab_on_all_screens(
    tmp_path,
    monkeypatch,
):
    fake_image = FakeImage()

    calls = []

    def fake_grab(
        all_screens=False,
    ):
        calls.append(
            all_screens
        )

        return fake_image

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        fake_grab,
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is True

    assert calls == [
        True
    ]


def test_screenshot_creates_screenshots_directory(
    tmp_path,
    monkeypatch,
):
    fake_image = FakeImage()

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: fake_image,
    )

    screenshots_directory = (
        tmp_path
        / "screenshots"
    )

    assert not screenshots_directory.exists()

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is True

    assert screenshots_directory.exists()
    assert screenshots_directory.is_dir()


def test_screenshot_uses_allowed_root(
    tmp_path,
    monkeypatch,
):
    fake_image = FakeImage()

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: fake_image,
    )

    allowed_root = (
        tmp_path
        / "authorized"
    )

    tool = ScreenshotTool(
        allowed_root=allowed_root,
    )

    result = tool.execute({})

    assert result.success is True
    assert result.output is not None

    screenshot_path = Path(
        result.output[
            "path"
        ]
    )

    assert screenshot_path.is_relative_to(
        allowed_root
    )

    assert screenshot_path.parent == (
        allowed_root
        / "screenshots"
    )


def test_screenshot_rejects_path_outside_allowed_root(
    tmp_path,
    monkeypatch,
):
    class OutsidePath:
        def __init__(
            self,
            path,
        ) -> None:
            self.path = Path(path)

        def resolve(
            self,
        ):
            return self

        def relative_to(
            self,
            _other,
        ):
            raise ValueError(
                "outside"
            )

        @property
        def parent(self):
            return self.path.parent

        @property
        def suffix(self):
            return self.path.suffix

        @property
        def name(self):
            return self.path.name

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    fake_image = FakeImage()

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: fake_image,
    )

    monkeypatch.setattr(
        "app.tools.pc_screenshot.Path.resolve",
        lambda self: OutsidePath(self),
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "fuori" in (
        result.error.lower()
    )


def test_screenshot_handles_directory_creation_error(
    tmp_path,
    monkeypatch,
):
    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    def fail_mkdir(
        *args,
        **kwargs,
    ):
        raise OSError(
            "Errore directory simulato"
        )

    monkeypatch.setattr(
        Path,
        "mkdir",
        fail_mkdir,
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "creare la directory" in (
        result.error.lower()
    )


def test_screenshot_handles_capture_oserror(
    tmp_path,
    monkeypatch,
):
    def fail_grab(
        all_screens=False,
    ):
        raise OSError(
            "Errore cattura simulato"
        )

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        fail_grab,
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "impossibile catturare" in (
        result.error.lower()
    )


def test_screenshot_handles_unexpected_capture_error(
    tmp_path,
    monkeypatch,
):
    def fail_grab(
        all_screens=False,
    ):
        raise RuntimeError(
            "Errore inatteso simulato"
        )

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        fail_grab,
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "errore durante la cattura" in (
        result.error.lower()
    )


def test_screenshot_handles_save_error(
    tmp_path,
    monkeypatch,
):
    class FailingImage:
        def save(
            self,
            path,
            format=None,
        ) -> None:
            raise OSError(
                "Errore salvataggio simulato"
            )

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: FailingImage(),
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is False
    assert result.error is not None

    assert "impossibile catturare" in (
        result.error.lower()
    )


def test_screenshot_handles_stat_error(
    tmp_path,
    monkeypatch,
):
    fake_image = FakeImage()

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: fake_image,
    )

    original_stat = Path.stat

    def fake_stat(
        self,
        *args,
        **kwargs,
    ):
        if self.parent.name == "screenshots":
            raise OSError(
                "Errore stat simulato"
            )

        return original_stat(
            self,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "stat",
        fake_stat,
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    result = tool.execute({})

    assert result.success is True
    assert result.output is not None

    assert result.output[
        "bytes"
    ] == 0


def test_screenshot_generates_unique_filename(
    tmp_path,
    monkeypatch,
):
    fake_image = FakeImage()

    monkeypatch.setattr(
        "app.tools.pc_screenshot.ImageGrab.grab",
        lambda all_screens=False: fake_image,
    )

    tool = ScreenshotTool(
        allowed_root=tmp_path,
    )

    first = tool.execute({})
    second = tool.execute({})

    assert first.success is True
    assert second.success is True

    assert first.output is not None
    assert second.output is not None

    first_path = Path(
        first.output[
            "path"
        ]
    )

    second_path = Path(
        second.output[
            "path"
        ]
    )

    assert first_path != second_path