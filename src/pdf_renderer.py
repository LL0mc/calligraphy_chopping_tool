"""PDF 渲染模块：将 PDF 每页渲染为高分辨率 PNG 图片"""
import os
import pypdfium2 as pdfium
from PIL import Image


def render_pdf_page(pdf_path: str, page_index: int, output_dir: str,
                    dpi_scale: int = 2) -> str:
    """渲染 PDF 的指定页为 PNG 图片

    Args:
        pdf_path: PDF 文件路径
        page_index: 页码索引（从0开始）
        output_dir: 输出目录
        dpi_scale: 渲染倍数

    Returns:
        输出图片的绝对路径
    """
    os.makedirs(output_dir, exist_ok=True)

    doc = pdfium.PdfDocument(pdf_path)
    page = doc[page_index]

    # 渲染为图片
    image = page.render(scale=dpi_scale)
    pil_image = image.to_pil().convert("RGB")

    # 保存
    output_path = os.path.join(output_dir, f"page_{page_index + 1:03d}.png")
    pil_image.save(output_path, "PNG")

    doc.close()

    print(f"[渲染] 第 {page_index + 1} 页 -> {output_path}")
    print(f"       尺寸: {pil_image.width} x {pil_image.height}")

    return output_path


def render_all_pages(pdf_path: str, output_dir: str, dpi_scale: int = 2,
                     page_range: tuple = None) -> list:
    """渲染 PDF 所有页或指定页码范围

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
        dpi_scale: 渲染倍数
        page_range: 页码范围 (start, end)，None 表示全部

    Returns:
        输出图片路径列表
    """
    doc = pdfium.PdfDocument(pdf_path)
    total_pages = len(doc)

    if page_range is None:
        start, end = 0, total_pages
    else:
        start = max(0, page_range[0] - 1)  # 转为0-based
        end = min(total_pages, page_range[1])

    output_paths = []
    for i in range(start, end):
        path = render_pdf_page(pdf_path, i, output_dir, dpi_scale)
        output_paths.append(path)

    doc.close()
    return output_paths
