# 中文使用说明

v0.4.0：分析面板自适应宽度，无需左右滚动。高级峰检测、Marker 组管理、自定义预设/锚点排列和校准诊断默认折叠。结果表保留常用列，选中条带后展开“所选条带详情”查看完整信息。新增 PageRuler Plus（10–250 kDa）及 PageRuler（10–180 kDa）具名预设与彩色参考条带；注意普通 PageRuler 的 25 kDa 是蓝色，只有 Plus 的 25 kDa 为橙红色。

英文主说明及完整部署步骤见 [README](../README.md)。目前仅支持 macOS；打包版适用于 Apple Silicon，无需安装 Python。默认英文，可从 **Language / 语言** 菜单选择简体中文，保存结果后重启生效。源码也可运行 `python -m wb_tools --language zh`。自定义预设与语言设置保存在 `~/Library/Application Support/WB Marker/`。

## WB Marker 分子量估算工具

一个本地运行的 GUI，用 WB 原图中 Marker lane 估算表观分子量（apparent molecular weight）。图片不会上传。

支持一次导入多个对齐通道：可在 Marker 专用通道提取峰，切换到目标蛋白通道后仍共享同一条选线和像素坐标，并可直接点击目标条带。

界面支持小屏幕：Marker 和目标分析页可用鼠标滚轮/触控板上下滚动；图片支持 `+`、`−`、一键适应窗口、滚动条，以及按住 Command（macOS）或 Control 后滚轮缩放。

## 安装与启动

需要 Python 3.10 或更高版本。

macOS 可直接双击 `run_wb_tool.command`；首次运行会在当前目录建立独立环境并安装运行依赖。也可以在终端手动运行：

```bash
python3 -m pip install -r requirements.txt
python3 main.py
```

macOS 如果系统 Python 缺少 Tkinter，建议安装 python.org 发行的 Python，或使用带 Tk 支持的 Conda Python。

## 使用方法

1. 点击“导入多张图片”，支持 PNG、JPEG、TIFF 和 BMP。多通道应具有相同尺寸且已经像素对齐。
2. 切换到 Marker 通道，选择“画 Marker 选线”，从加样孔方向沿 Marker lane 中心拖到胶底。每画一条线会新增一个独立的 `Marker 1 / Marker 2 / ...` 校准组。
3. 在“Marker 泳道组”列表选择要编辑的组。每一组独立保存图片通道、选线、峰位置、峰宽、kDa、拟合和 CV 误差。
4. 程序提取所选组的反相灰度强度并自动寻找暗条带峰。可调平滑、突出度、峰间距和选线宽度，再点“重新检测峰”。
5. 在曲线上点击可以手动增加峰；点击已有峰附近可删除。双击表格的 kDa 单元格，填写该组对应的 Marker 分子量。
6. 每组可分别选择内置或自定义预设。“应用完整预设”会依次填写当前选中的 Marker 组；也可从任一已知峰向下自动排列。
7. 可继续在同一或其他图片通道画新的 Marker 泳道并分别赋值。完成后点击“完成 Marker 并立即拟合 →”，程序会拟合所有有效 Marker 组。

8. 在第二阶段切换到目标通道，选择“添加目标泳道”，从泳道顶部沿中心拖到泳道底部。选线半宽控制实际平均的泳道范围；每条泳道会自动检测全部峰。
9. 在“已添加泳道”中选择任意泳道，可单独重新识别；点击其灰度曲线可手动增加或删除条带峰。
10. 最终结果按 `Lane → Band` 展示采用的 Marker 组、局部估算值、不确定范围、可信度、建议报告文字和范围状态。
11. 保存结果时可选择 CSV、XLSX 或 JSON，同时生成逐 Marker 校准报告和诊断图。

## 分子量计算方法

默认结果不再来自整段 Marker 的单一直线，而是使用目标位置上下最近的两个 Marker，在 `position_px` 与 `log10(MW)` 之间做局部线性插值：

```text
logMW = log10(MW1) + (x-x1)/(x2-x1) × (log10(MW2)-log10(MW1))
MW_local = 10^logMW
```

全局模型仍会计算：

```text
log10(MW_kDa) = slope × position_px + intercept
```

但它仅用于输出 `apparent_MW_global_kDa`、R²、log10 RMSE 和 Marker back-calculation error。最终推荐值为 `apparent_MW_local_kDa`。Local 与 global 相差超过 10% 时会自动产生警告。

### 多 Marker 组自动择优

每个目标 band 会分别使用所有已成功拟合的 Marker 组计算结果。选择顺序为：

1. 优先选择目标位置落在该 Marker 组覆盖范围内的正常 interpolation；
2. 其次考虑 near-boundary；只有没有正常覆盖时才采用 extrapolation；
3. 在相同范围状态下，选择由 local CV、band 峰宽和 Marker 峰宽共同得到的综合不确定度最低者；
4. 再以 confidence 和 local/global 差异作为平局判据。

因此并不是简单选择 R² 最高的 Marker，而是针对每一个目标条带分别选择最可靠的局部校准。输出会记录 `marker_group_used`、`marker_groups_compared` 和 `marker_selection_reason`，便于审计。

## 不确定度与可信度

- 对每个内部 Marker 做 leave-one-out：移除该点，用上下 Marker 局部插值预测它，再计算相对误差。
- 目标 band 优先使用相邻 Marker 的 LOO-CV 误差；局部信息不足时使用所有内部 Marker 的 CV 中位误差。
- 峰宽使用灰度峰的 FWHM。中心位置不确定度取 `max(2 px, FWHM/4)`；`±2 px` 是无法从窄峰获得更可靠信息时的保守下限。
- 相邻 Marker 的位置不确定度与 band 位置不确定度按平方和组合。
- 校准误差与位置误差在 log10(MW) 空间合并，再转换成 `MW_lower_kDa` 和 `MW_upper_kDa`。
- `high / medium / low / very_low` 由局部 CV 误差、位置误差、local/global 差异、Marker 间隔、边界位置和是否外推综合评分，不依赖单一阈值。
- 超出最高或最低 Marker 时分别标记 `extrapolation_high_MW` 或 `extrapolation_low_MW`，可信度强制为 `very_low`，并优先报告 `>最高 Marker` 或 `<最低 Marker`。

## 输出文件

主 CSV/XLSX 的每条 band 包括：

```text
lane, channel, band, marker_group_used, marker_groups_compared
marker_selection_reason, position_px, peak_width_px, position_uncertainty_px
nearest_upper_marker_kDa, nearest_upper_marker_position_px
nearest_lower_marker_kDa, nearest_lower_marker_position_px
apparent_MW_local_kDa, apparent_MW_global_kDa
local_global_difference_percent
MW_lower_kDa, MW_upper_kDa, relative_uncertainty_percent
range_status, confidence, reported_MW, reported_MW_text, warnings
```

每次保存还会在同一目录生成：

- `lane_summary.csv`：每行一个泳道，将该泳道的 `Band 1 / Band 2 / ...` 建议分子量排列在同一行，并汇总位置、采用的 Marker 组、可信度和警告数；
- `calibration_report.csv`：按 Marker 组列出每个 Marker 的 global 回算误差与 local leave-one-out 误差；
- `fit_summary.csv`：global regression 与 local CV 汇总指标；
- `calibration_diagnostic*.svg`：各 Marker 组的 Marker 点、global 直线、local 分段线和 global residual；
- `calibration_error_vs_mw*.svg`：各 Marker 组的 global 与 local LOO 相对误差随 Marker MW 的变化。

选择 XLSX 时，`Lane summary` 位于第一个工作表，逐条带原始结果保存在 `Band results`，因此既方便按泳道比较，也不会丢失详细结果。

## 回归测试示例

示例 Marker 为 `600@25, 400@94, 250@124, 230@141, 130@215, 110@307, 75@362, 45@422, 20@478`。当前测试得到：

| band position | Local kDa | Global kDa | 建议报告 |
|---:|---:|---:|---|
| 54.9 px | 503.3 | 463.0 | `~500 kDa` |
| 77.9 px | 439.7 | 396.9 | `~440 kDa` |
| 94.3 px | 398.1 | 355.7 | `~400 kDa` |
| 195 px | 151.7 | 181.3 | `~150 kDa` |
| 272 px | 117.2 | 108.3 | `~120 kDa` |

因此接近 `400 kDa @ 94 px` 的目标条带会自然得到约 400 kDa，而不会再默认采用 global regression 的约 356 kDa。

## 实验与解释注意事项

- 建议按从高分子到低分子的顺序画线，并确认 Marker kDa 随迁移位置整体递减。
- `R²` 反映这些 Marker 点在线性模型下的一致性，但不能消除胶浓度、转膜、糖基化、聚集或 SDS 结合异常带来的系统误差。
- 超出 Marker 覆盖范围属于外推，应报告较宽范围或 `> 某值`，不要给出虚假的小数精度。
- 工具输出应写作“表观分子量约为 … kDa”，而非精确真实分子量。
