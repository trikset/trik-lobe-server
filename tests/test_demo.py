# Copyright 2026 Iakov Kirilenko. Licensed under the Apache License, Version 2.0.
# ruff: noqa: FBT001  # tests parametrize bools
# pyright: reportPrivateUsage=false
# pylint: disable=W0212  # tests drive private frame/phase state directly

from unittest.mock import MagicMock, patch

import pytest

from trik_mind.demo import DemoSource


def _make(fps: float = 16.0) -> tuple[MagicMock, DemoSource]:
    fmt = MagicMock()
    return fmt, DemoSource(fmt, fps=fps)


class TestDist:
    @pytest.mark.parametrize(
        ("scenario", "ix", "expected_conf"),
        [("high", 0, 0.94), ("peach", 1, 0.85), ("spread", 2, 0.82), ("hold", 3, 0.55), ("low", 0, 0.36)],
    )
    def test_base_distributions(self, scenario: str, ix: int, expected_conf: float) -> None:
        _, src = _make()
        with patch("trik_mind.demo.random.uniform", return_value=0.0):
            label, conf, labels = src._dist(ix, scenario)
        assert label == DemoSource.LABELS[ix]
        assert conf == pytest.approx(expected_conf)
        # sorted desc by confidence, wrapped around the label pool
        assert [lbl for lbl, _ in labels] == [DemoSource.LABELS[(ix + i) % 4] for i in range(4)]
        assert [c for _, c in labels] == sorted((c for _, c in labels), reverse=True)

    def test_jitter_applied_max_floor(self) -> None:
        _, src = _make()
        # -0.5 jitter would push 0.94 to 0.44 and 0.01-floor three others
        with patch("trik_mind.demo.random.uniform", return_value=-0.5):
            _, conf, labels = src._dist(0, "high")
        assert conf == pytest.approx(0.44)
        assert all(c >= 0.01 for _, c in labels)


class TestStepRouting:
    def test_error_phase_emits_on_error(self) -> None:
        fmt, src = _make()
        with patch("trik_mind.demo.time.sleep"), patch("trik_mind.demo.random.uniform", return_value=0.0):
            src._phase_countdown = 5
            src._phase = "error"
            src._frames_left = 1
            src.step()
        fmt.on_error.assert_called_once()
        fmt.on_prediction.assert_not_called()

    @pytest.mark.parametrize(
        ("phase", "sent"),
        [("hold", False), ("high", True), ("peach", True), ("spread", True)],
    )
    def test_confident_phases_emit_prediction(self, phase: str, sent: bool) -> None:
        fmt, src = _make()
        with patch("trik_mind.demo.time.sleep"), patch("trik_mind.demo.random.uniform", return_value=0.0):
            src._phase_countdown = 5
            src._phase = phase
            src._frames_left = 1
            src.step()
        call = fmt.on_prediction.call_args
        assert call is not None
        assert call.kwargs["sent"] is sent
        fmt.on_error.assert_not_called()

    def test_low_phase_below_view_emits_on_error(self) -> None:
        fmt, src = _make()
        with patch("trik_mind.demo.time.sleep"), patch("trik_mind.demo.random.uniform", return_value=0.0):
            src._phase_countdown = 5
            src._phase = "low"
            src._frames_left = 1
            src.step()
        fmt.on_error.assert_called_once()
        fmt.on_prediction.assert_not_called()

    def test_timing_floor_clamped_at_two_ms(self) -> None:
        fmt, src = _make(fps=1000.0)  # period = 1 ms < floor
        with patch("trik_mind.demo.time.sleep"), patch("trik_mind.demo.random.uniform", return_value=-0.15):
            src._phase_countdown = 5
            src._phase = "high"
            src._frames_left = 1
            src.step()
        timing = fmt.on_prediction.call_args.args[2]
        assert timing == 0.002


class TestStepPhasePicker:
    @pytest.mark.parametrize(
        ("r", "phase"),
        [(0.05, "error"), (0.2, "low"), (0.35, "peach"), (0.55, "hold"), (0.9, "high")],
    )
    def test_picker_selects_phase(self, r: float, phase: str) -> None:
        _, src = _make()
        with (
            patch("trik_mind.demo.time.sleep"),
            patch("trik_mind.demo.random.random", return_value=r),
            patch("trik_mind.demo.random.uniform", return_value=10.0),
        ):
            src._phase_countdown = 0  # force picker on the next step
            src._frames_left = 1
            src.step()
        assert src._phase == phase


class TestFrameGating:
    def test_emits_every_5th_frame(self) -> None:
        fmt, src = _make()
        with patch("trik_mind.demo.time.sleep"), patch("trik_mind.demo.random.uniform", return_value=0.0):
            src._phase_countdown = 10
            src._frames_left = 1  # first step emits immediately
            for _ in range(6):  # 1 + 5 = 6 frames → 2 emissions
                src.step()
        assert fmt.on_prediction.call_count == 2

    def test_sleep_between_emissions(self) -> None:
        fmt, src = _make(fps=10.0)
        with (
            patch("trik_mind.demo.time.sleep") as mock_sleep,
            patch("trik_mind.demo.random.uniform", return_value=0.0),
        ):
            src._phase_countdown = 10
            src._frames_left = 2
            src.step()  # frame skip → sleep period, no emit
            src.step()  # frame emit → sleep period
        fmt.on_prediction.assert_called_once()
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[1].args[0] == pytest.approx(0.1)


class TestRun:
    def test_run_loops_until_keyboard_interrupt(self) -> None:
        fmt, src = _make()
        with patch.object(src, "step", side_effect=KeyboardInterrupt), pytest.raises(KeyboardInterrupt):
            src.run()
        fmt.close.assert_not_called()
