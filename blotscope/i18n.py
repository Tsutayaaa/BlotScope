"""English/Chinese UI messages and user preferences, independent of Tk."""
from __future__ import annotations
import json
import os
from pathlib import Path


def config_dir() -> Path:
    directory = Path.home() / "Library" / "Application Support" / "BlotScope"
    legacy = directory.with_name("WB Marker")
    if not directory.exists() and legacy.is_dir():
        import shutil
        shutil.copytree(legacy, directory)
    return directory


def _initial_language() -> str:
    override = os.environ.get("BLOTSCOPE_LANGUAGE") or os.environ.get("WB_MARKER_LANGUAGE")
    if override in ("en", "zh"):
        return override
    try:
        saved = json.loads((config_dir() / "settings.json").read_text(encoding="utf-8"))
        language = saved.get("language", "en")
        return language if language in ("en", "zh") else "en"
    except (OSError, ValueError, AttributeError, TypeError):
        return "en"


_language = _initial_language()


def set_language(language: str) -> None:
    global _language
    if language not in ("en", "zh"):
        raise ValueError("Unsupported language: " + language)
    _language = language


def save_language(language: str) -> None:
    if language not in ("en", "zh"):
        raise ValueError("Unsupported language: " + language)
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "settings.json"
    temporary = directory / "settings.json.tmp"
    temporary.write_text(json.dumps({"language": language}), encoding="utf-8")
    temporary.replace(target)


def translate(message: str) -> str:
    return ENGLISH.get(message, message) if _language == "en" else message


ENGLISH = {'BlotScope 分子量估算工具': 'BlotScope — Molecular Weight Estimator',
 '适应窗口': 'Fit to window',
 'Marker 尚未拟合': 'Markers not fitted',
 '请先导入 WB 原图。': 'Import your WB images to begin.',
 '1  导入多张图片': '1  Import images',
 '当前通道': 'Channel',
 '清除选线': 'Clear selection',
 '保存结果': 'Save results',
 '图片操作：': 'Image mode:',
 '画 Marker 选线': 'Draw marker lane',
 '添加目标泳道': 'Add target lane',
 '在 Marker 通道画线；目标通道共享坐标。': 'Draw on the marker channel; coordinates are shared.',
 '1  Marker 定标': '1  Marker calibration',
 '2  目标泳道分析': '2  Target lane analysis',
 '确认峰与 kDa 后：': 'Check peaks and kDa:',
 '完成 Marker 并立即拟合  →': 'Fit markers & continue →',
 'Marker 泳道组（逐组选择并设置 kDa）': 'Marker groups — select and assign kDa',
 'Marker组': 'Marker group',
 '通道': 'Channel',
 '峰数': 'Peaks',
 '状态': 'Status',
 '删除所选': 'Remove selected',
 '在图上继续画线\n即可添加新组': 'Draw another lane\nto add a group',
 '峰检测': 'Peak detection',
 '平滑半径 (px)': 'Smoothing radius (px)',
 '最小峰突出度 (%)': 'Min. prominence (%)',
 '最小峰间距 (px)': 'Min. peak spacing (px)',
 '选线半宽 (px)': 'Lane half-width (px)',
 '重新检测峰': 'Detect peaks again',
 'Marker 预设与自动排列': 'Marker presets & assignment',
 '另存为新预设': 'Save new preset',
 '应用完整预设': 'Apply full preset',
 '选中一个峰，指定它对应：': 'Selected peak corresponds to:',
 '从选中峰开始向下自动排列': 'Assign downward from selected peak',
 '峰位置与 Marker kDa（可留空）': 'Peak positions & marker kDa (optional)',
 '沿线位置 (px)': 'Position (px)',
 '双击 kDa 单元格编辑；点击曲线可增删峰。': 'Double-click kDa to edit; click the plot to add/remove peaks.',
 'Marker 拟合': 'Marker fit',
 '拟合 log10(MW)–位置': 'Fit log10(MW) vs position',
 '拟合完成后，上方按钮会自动进入目标泳道分析。': 'Use the button above to fit and continue to target analysis.',
 '切换到目标通道，选择“添加目标泳道”，从胶顶沿泳道中心拖到胶底。选线半宽决定泳道范围。': 'Switch to the target channel and select “Add target lane”. '
                                                'Drag down the lane center from top to bottom. Half-width '
                                                'sets the sampling area.',
 '目标泳道检测参数': 'Target peak detection',
 '平滑': 'Smooth',
 '突出度%': 'Prom. %',
 '峰距px': 'Spacing px',
 '半宽px': 'Half-width px',
 '重新识别所选泳道': 'Re-detect selected lane',
 '删除所选泳道': 'Remove selected lane',
 '已添加泳道': 'Target lanes',
 '泳道': 'Lane',
 '条带数': 'Bands',
 '所选泳道灰度曲线（点击曲线可手动增加/删除条带峰）': 'Selected lane profile — click to add/remove peaks',
 '每个泳道的条带结果': 'Band results by lane',
 '条带': 'Band',
 '采用Marker': 'Marker used',
 '位置 px': 'Position px',
 '不确定范围 kDa': 'Range kDa',
 '可信度': 'Confidence',
 '建议报告': 'Report as',
 '范围状态': 'Range status',
 '已完成 {0} 组 Marker 拟合；目标条带将自动选择不确定度最低的校准组。': 'Fitted {0} marker groups; target bands use the best available '
                                             'local calibration.',
 '图片': 'Images',
 '所有文件': 'All files',
 '无法打开图片': 'Cannot open images',
 '；注意：图片尺寸不同，请确认坐标已经对齐': '; image sizes differ — verify pixel alignment',
 '已导入 {0} 个通道{1}': 'Imported {0} channels{1}',
 '部分图片未导入': 'Some images were not imported',
 '当前通道：{0}': 'Current channel: {0}',
 '请先完成 Marker 拟合': 'Fit markers first',
 'Marker 拟合完成后才能添加目标泳道。': 'Fit the marker calibration before adding target lanes.',
 '请先画 Marker 线': 'Draw a marker lane first',
 '先在任一 Marker 通道沿迁移方向画线，再切换目标通道点击条带。': 'Draw a lane along migration on a marker channel, then switch to the '
                                       'target channel to select a band.',
 '已从 {0} 选择目标条带：{1:.1f} px': 'Selected target band in {0}: {1:.1f} px',
 '目标': 'Target',
 '泳道范围太短': 'Lane too short',
 '请从泳道顶部沿中心拖到泳道底部。': 'Drag along the lane center from top to bottom.',
 '已添加 {0}，自动识别到 {1} 条目标条带。': 'Added {0}; detected {1} target bands.',
 'Marker 尚未拟合。': 'Markers not fitted.',
 '添加并选择泳道后显示灰度曲线': 'Add and select a lane to display its intensity profile',
 '泳道起点': 'Lane start',
 '泳道终点': 'Lane end',
 '请选择泳道': 'Select a lane',
 '请先选择一个泳道。': 'Please select a lane first.',
 '{0} 已重新识别：{1} 个条带。': 'Re-detected {0}: {1} bands.',
 '已删除 {0}。': 'Removed {0}.',
 'Marker 泳道太短': 'Marker lane too short',
 '请从 Marker 泳道顶部沿中心拖到泳道底部。': 'Drag along the marker lane center from top to bottom.',
 '已添加 {0}，检测到 {1} 个峰；请为本组设置 Marker kDa。': 'Added {0}; detected {1} peaks. Assign marker kDa for this group.',
 '已拟合': 'Fitted',
 '已赋值 {0}': 'Assigned {0}',
 '正在编辑 {0}；预设和手动 kDa 只作用于这一组。': 'Editing {0}; presets and manual kDa apply only to this group.',
 '请先选线': 'Select a lane first',
 '请在图片上沿 Marker lane 拖出一条线。': 'Drag a line along the marker lane in the image.',
 '在 {0} 检测到 {1} 个峰；可在曲线上点击增删。': 'Detected {1} peaks in {0}; click the plot to add/remove peaks.',
 '选线后显示灰度强度曲线': 'Select a lane to display its intensity profile',
 '数值无效': 'Invalid value',
 'kDa 必须是大于 0 的数字。': 'kDa must be a finite number greater than zero.',
 '预设无效': 'Invalid preset',
 '保存 Marker 预设': 'Save marker preset',
 '请输入新预设名称：': 'Enter a name for the new preset:',
 '保存预设失败': 'Could not save preset',
 '已保存 Marker 预设：{0}': 'Saved marker preset: {0}',
 '没有峰': 'No peaks',
 '请先检测或手动添加峰。': 'Detect peaks or add them manually first.',
 '已按迁移顺序填写 {0} 个 Marker。': 'Assigned {0} markers in migration order.',
 '请选择锚点': 'Select an anchor peak',
 '请先在峰表中选中一个已知条带。': 'Select a known band in the peak table first.',
 '锚点无效': 'Invalid anchor',
 '锚点不在预设中': 'Anchor not in preset',
 '锚点 kDa 必须是当前预设中的一个数值。': 'The anchor kDa must be one of the values in the current preset.',
 '从 {0:g} kDa 锚点开始，已向下自动排列 {1} 个条带。': 'Assigned {1} bands downward from the {0:g} kDa anchor.',
 '没有可用的 Marker 拟合': 'No valid marker calibration',
 '已拟合 {0} 组 Marker｜逐 band 自动择优｜当前总体最佳 {1}（CV中位误差 {2:.1f}%）': 'Fitted {0} groups | per-band selection | best '
                                                             'overall: {1} (median CV error {2:.1f}%)',
 '部分 Marker 组未参与': 'Some marker groups were excluded',
 '无法拟合': 'Cannot fit calibration',
 '优秀': 'Excellent',
 '良好': 'Good',
 '需检查峰对应关系': 'Check peak assignments',
 '默认结果：邻近 Marker local log-linear interpolation\nlog10(MW) = {0:.6f} × position + {1:.5f}\nGlobal 诊断：{2}，R²={3:.4f}，RMSE={4:.4f}\nGlobal 平均/最大误差={5:.2f}% / {6:.2f}%\nLocal LOO-CV 中位/平均/最大误差={7:.2f}% / {8:.2f}% / {9:.2f}%': 'Default: '
                                                                                                                                                                                                                               'local '
                                                                                                                                                                                                                               'log-linear '
                                                                                                                                                                                                                               'interpolation '
                                                                                                                                                                                                                               'between '
                                                                                                                                                                                                                               'adjacent '
                                                                                                                                                                                                                               'markers\n'
                                                                                                                                                                                                                               'Global '
                                                                                                                                                                                                                               'log10(MW) '
                                                                                                                                                                                                                               '= '
                                                                                                                                                                                                                               '{0:.6f} '
                                                                                                                                                                                                                               '× '
                                                                                                                                                                                                                               'position '
                                                                                                                                                                                                                               '+ '
                                                                                                                                                                                                                               '{1:.5f}\n'
                                                                                                                                                                                                                               'Global '
                                                                                                                                                                                                                               'diagnostics: '
                                                                                                                                                                                                                               '{2}, '
                                                                                                                                                                                                                               'R²={3:.4f}, '
                                                                                                                                                                                                                               'RMSE={4:.4f}\n'
                                                                                                                                                                                                                               'Global '
                                                                                                                                                                                                                               'mean/max '
                                                                                                                                                                                                                               'error={5:.2f}% '
                                                                                                                                                                                                                               '/ '
                                                                                                                                                                                                                               '{6:.2f}%\n'
                                                                                                                                                                                                                               'Local '
                                                                                                                                                                                                                               'LOO-CV '
                                                                                                                                                                                                                               'median/mean/max '
                                                                                                                                                                                                                               'error={7:.2f}% '
                                                                                                                                                                                                                               '/ '
                                                                                                                                                                                                                               '{8:.2f}% '
                                                                                                                                                                                                                               '/ '
                                                                                                                                                                                                                               '{9:.2f}%',
 '默认 Local 插值｜Global R²={0:.4f}｜Local CV中位误差={1:.1f}%': 'Local interpolation | Global R²={0:.4f} | Median '
                                                        'local CV error={1:.1f}%',
 '拟合完成。目标条带位置应使用同一条选线起点的像素距离。': 'Calibration complete. Target positions must use the same migration origin '
                                'in pixels.',
 '位置无效': 'Invalid position',
 '请输入目标条带沿相同迁移方向的位置（像素）。': 'Enter the target band position along the same migration direction (pixels).',
 '目标条带位置不能小于 0。': 'Target band position cannot be negative.',
 '没有结果': 'No results',
 '请先选线并检测峰。': 'Select a lane and detect peaks first.',
 '保存 XLSX 需要 openpyxl，请运行：python3 -m pip install openpyxl': 'XLSX export requires openpyxl. Run: python3 -m '
                                                            'pip install openpyxl',
 '结果和 calibration diagnostics 已保存到：{0}': 'Results and calibration diagnostics saved to: {0}',
 '保存失败': 'Save failed',
 '缺少 Pillow。请先运行：python3 -m pip install Pillow': 'Pillow is missing. Run: python3 -m pip install Pillow',
 '至少需要两个 Marker 点。': 'At least two marker points are required.',
 'Marker kDa 必须大于 0。': 'Marker positions must be finite and kDa values must be finite and positive.',
 'Marker 峰位置不能重复。': 'Marker peak positions must be unique.',
 'Marker kDa 必须随迁移位置增加而递减；请检查峰与预设的对应顺序。': 'Marker kDa must decrease with migration position; check peak '
                                          'assignments.',
 '局部插值至少需要两个 Marker。': 'Local interpolation requires at least two markers.',
 '没有可用于该条带的 Marker 校准组。': 'No marker calibration is available for this band.',
 '拟合至少需要两个具有 kDa 数值的峰。': 'Fitting requires at least two peaks with assigned kDa values.',
 '拟合峰不能位于同一位置。': 'Calibration peaks cannot all have the same position.',
 '预设1（600–20 kDa）': 'Preset 1 (600–20 kDa)',
 '预设2（170–10 kDa）': 'Preset 2 (170–10 kDa)',
 '预设只能包含用空格或逗号分隔的数字。': 'Use numbers separated by spaces or commas in presets.',
 '预设至少需要一个大于 0 的 kDa 数值。': 'Presets require at least one finite, positive kDa value.',
 '请按从高分子到低分子的顺序输入预设。': 'Enter preset values in descending molecular weight order.'}

ENGLISH.update({
    "管理 Marker 泳道组": "Manage marker groups",
    "高级峰检测参数": "Advanced peak detection",
    "Marker 预设": "Marker preset · kDa",
    "自定义预设与锚点排列": "Custom preset & anchor assignment",
    "Marker 峰与 kDa": "Marker peaks & kDa",
    "校准诊断详情": "Calibration diagnostics",
    "所选条带详情": "Selected band details",
})
