"""Layout Agent —— 拆解排版与文字架构。

对应技术方案「五、Design Agent」中的「排版」与「六、视觉拆解」的信息层级维度，
补齐版式类型、信息层级、对齐、留白、标题处理、字体调性等文字/排版层面的拆解。

基于边缘密度的区域分布（上/中/下、左/中/右）与文字密度估计版式结构。
"""
from __future__ import annotations

from ..schemas import Layout, Typography
from ..vision_provider import ImageFeatures


def _dominant_band(band: tuple[float, float, float]) -> str:
    labels = ["上部", "中部", "下部"]
    return labels[band.index(max(band))]


def _alignment(col: tuple[float, float, float]) -> str:
    left, center, right = col
    if center >= left and center >= right and center - min(left, right) > 0.03:
        return "居中对齐"
    if left > right + 0.03:
        return "左对齐"
    if right > left + 0.03:
        return "右对齐"
    return "两端 / 网格对齐"


def run(features: ImageFeatures) -> tuple[Layout, Typography]:
    band = features.band_activity
    col = features.col_activity
    dom = _dominant_band(band)
    alignment = _alignment(col)
    spread = max(band) - min(band)

    # —— 版式类型 ——
    if features.complexity < 0.25:
        layout_type = "留白型 / 极简版式"
        whitespace = "大面积留白，信息高度聚焦"
    elif spread > 0.12 and dom in ("上部", "下部"):
        layout_type = f"{'上下' if features.orientation != 'landscape' else '横向'}分区型（{dom}为信息重心）"
        whitespace = f"信息集中在{dom}，另一侧留白呼吸"
    elif features.text_density > 0.28:
        layout_type = "网格型 / 多信息模块"
        whitespace = "留白偏紧，模块化排布，信息量大"
    else:
        layout_type = "中轴型 / 居中构图"
        whitespace = "上下留白均衡，主体居中"

    # —— 信息层级 ——
    hierarchy: list[str] = []
    if spread > 0.1:
        hierarchy.append(f"主标题（位于{dom}，视觉最强）")
        hierarchy.append("副标题 / 说明性文字")
    else:
        hierarchy.append("主视觉主体（图形优先）")
        hierarchy.append("点缀性标题 / 标签")
    if features.text_density > 0.2:
        hierarchy.append("正文 / 列表信息")
    hierarchy.append("辅助信息（logo、注释、按钮）")

    focal = f"视觉重心在{dom}，阅读路径由{dom}向{'下' if dom != '下部' else '上'}延展"

    # —— 硬版式参数 ——
    cg = features.col_groups
    if cg <= 1:
        grid_columns = "单列 / 通栏"
    elif cg == 2:
        grid_columns = "双栏（2 列栅格）"
    elif cg == 3:
        grid_columns = "三栏（3 列栅格）"
    else:
        grid_columns = f"多栏网格（约 {cg} 列）"

    rb = features.row_blocks
    modules = f"纵向约 {rb} 个内容模块" if rb else "整体一块 / 无明显分区"

    mt, mr, mb, ml = features.margins
    avg_margin = (mt + mr + mb + ml) / 4
    if avg_margin > 0.15:
        margin_desc = "宽边距（四周大留白）"
    elif avg_margin > 0.07:
        margin_desc = "中等边距"
    else:
        margin_desc = "窄边距 / 近满版"
    margins = (
        f"{margin_desc}：上{int(mt*100)}% 下{int(mb*100)}% 左{int(ml*100)}% 右{int(mr*100)}%"
    )

    # 模块间距 / 疏密（用内容占比与模块数估计）
    if features.content_ratio > 0.7 and rb >= 3:
        spacing = "模块紧凑、间距小，信息密集"
    elif features.content_ratio < 0.4:
        spacing = "模块稀疏、间距大，留白呼吸充分"
    else:
        spacing = "模块间距适中，疏密均衡"

    content_ratio_desc = f"内容区约占画面 {int(features.content_ratio*100)}%"

    layout = Layout(
        layout_type=layout_type,
        alignment=alignment,
        hierarchy=hierarchy,
        whitespace=whitespace,
        focal=focal,
        grid_columns=grid_columns,
        modules=modules,
        margins=margins,
        spacing=spacing,
        content_ratio=content_ratio_desc,
        grid_metrics={
            "columns": float(cg),
            "row_blocks": float(rb),
            "content_ratio": float(features.content_ratio),
            "margin_top": float(mt),
            "margin_right": float(mr),
            "margin_bottom": float(mb),
            "margin_left": float(ml),
        },
        description=(
            f"{layout_type}，{alignment}；{grid_columns}，{modules}；{margin_desc}；"
            f"{content_ratio_desc}。{whitespace}。"
        ),
    )

    # —— 文字 / 标题 / 字体 ——
    # 标题处理
    if spread > 0.12:
        title_treatment = "大字号主标题，与画面强对比、抢占视觉焦点"
    elif features.complexity < 0.25:
        title_treatment = "克制小标题，靠留白凸显，不喧宾夺主"
    else:
        title_treatment = "标题与图形融合排布，图文一体"

    # 字体调性（结合风格倾向）
    if features.saturation < 0.3 and features.brightness < 0.5:
        font_tone = "高级无衬线（细黑体 / 几何无衬线），冷静克制"
    elif features.warm and features.saturation > 0.4:
        font_tone = "圆润 / 手写体倾向，亲和有温度"
    elif features.contrast > 0.45:
        font_tone = "粗衬线 / 高对比字体，力量感强"
    else:
        font_tone = "现代无衬线（如思源黑体 / Inter），通用百搭"

    # 字号对比
    size_contrast = (
        "字号层级对比强（标题远大于正文）" if spread > 0.12 else "字号层级平缓，整体统一"
    )

    # 文字占比
    if features.text_density > 0.28:
        text_ratio = "重文字型（信息密集）"
    elif features.text_density < 0.12:
        text_ratio = "以图为主（文字点缀）"
    else:
        text_ratio = "图文均衡"

    pairing = "中文主字 + 英文/数字辅助，主辅两级搭配"

    typography = Typography(
        title_treatment=title_treatment,
        font_tone=font_tone,
        size_contrast=size_contrast,
        pairing=pairing,
        text_ratio=text_ratio,
        description=f"{text_ratio}；{title_treatment}；建议字体：{font_tone}；{size_contrast}。",
    )

    return layout, typography
