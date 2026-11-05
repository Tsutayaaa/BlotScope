import ast
from pathlib import Path
from string import Formatter
import pytest
from blotscope import i18n

@pytest.fixture(autouse=True)
def restore_language():
    old = i18n._language
    yield
    i18n.set_language(old)


def test_languages_and_fallback():
    i18n.set_language('en')
    assert i18n.translate('保存结果') == 'Save results'
    assert i18n.translate('custom marker') == 'custom marker'
    i18n.set_language('zh')
    assert i18n.translate('保存结果') == '保存结果'
    with pytest.raises(ValueError):
        i18n.set_language('fr')


def test_all_message_placeholders_match():
    def fields(text):
        return sorted((field, spec, conversion) for _, field, spec, conversion in Formatter().parse(text) if field is not None)
    for source, translated in i18n.ENGLISH.items():
        assert fields(source) == fields(translated), source


def test_all_translation_calls_have_english_messages():
    root = Path(__file__).resolve().parents[1] / 'blotscope'
    for filename in ('gui.py', 'core.py'):
        for node in ast.walk(ast.parse((root / filename).read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_':
                assert isinstance(node.args[0], ast.Constant)
                assert node.args[0].value in i18n.ENGLISH


def test_preferences_and_override(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, 'config_dir', lambda: tmp_path)
    monkeypatch.delenv('WB_MARKER_LANGUAGE', raising=False)
    assert i18n._initial_language() == 'en'
    i18n.save_language('zh')
    assert i18n._initial_language() == 'zh'
    monkeypatch.setenv('WB_MARKER_LANGUAGE', 'en')
    assert i18n._initial_language() == 'en'
    monkeypatch.delenv('WB_MARKER_LANGUAGE')
    (tmp_path / 'settings.json').write_text('invalid json')
    assert i18n._initial_language() == 'en'


def test_readme_api_example():
    from blotscope.core import prepare_markers, linear_fit, estimate_band
    positions = [25, 94, 124, 141, 215, 307, 362, 422, 478]
    weights = [600, 400, 250, 230, 130, 110, 75, 45, 20]
    result = estimate_band(prepare_markers(positions, weights), linear_fit(positions, weights), position_px=94.3, peak_width_px=8)
    assert 397 < result.apparent_mw_local_kda < 399
