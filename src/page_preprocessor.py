"""页面预处理模块：灰度化、二值化、裁剪边距、增强"""
import cv2
import numpy as np
from PIL import Image


def load_image(image_path: str) -> np.ndarray:
    """加载图片并转为灰度图

    Args:
        image_path: 图片路径

    Returns:
        灰度图 numpy array
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"无法加载图片: {image_path}")
    return img


def detect_content_bbox(gray: np.ndarray, margin_threshold: int = 50,
                        min_content_ratio: float = 0.02) -> tuple:
    """检测内容区域边界框

    通过行列投影找到有实际内容的区域，裁剪掉空白边距

    Args:
        gray: 灰度图
        margin_threshold: 判定为"有内容"的像素阈值（<此值为深色）
        min_content_ratio: 最小内容占比（该行列深色像素占比超过此值才算有内容）

    Returns:
        (y_min, y_max, x_min, x_max) 内容区域边界
    """
    h, w = gray.shape

    # 二值化
    _, binary = cv2.threshold(gray, margin_threshold, 255, cv2.THRESH_BINARY_INV)

    # 水平投影
    h_proj = np.sum(binary > 0, axis=1)
    content_rows = np.where(h_proj > w * min_content_ratio)[0]

    # 垂直投影
    v_proj = np.sum(binary > 0, axis=0)
    content_cols = np.where(v_proj > h * min_content_ratio)[0]

    if len(content_rows) == 0 or len(content_cols) == 0:
        return (0, h, 0, w)

    y_min = max(0, content_rows[0] - 5)
    y_max = min(h, content_rows[-1] + 5)
    x_min = max(0, content_cols[0] - 5)
    x_max = min(w, content_cols[-1] + 5)

    return (y_min, y_max, x_min, x_max)


def remove_grid_lines(gray: np.ndarray, max_thickness: int = 8) -> np.ndarray:
    """去除网格线（竖线/横线）

    使用形态学操作检测并去除细长的网格线，保留手写字符

    Args:
        gray: 灰度图
        max_thickness: 网格线最大粗细

    Returns:
        去除网格线后的灰度图
    """
    _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY_INV)

    # 检测水平线
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel, iterations=2)

    # 检测垂直线
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel, iterations=2)

    # 合并网格线
    grid_mask = cv2.bitwise_or(h_lines, v_lines)

    # 从原图中去除网格线
    cleaned = cv2.bitwise_and(binary, cv2.bitwise_not(grid_mask))

    # 转回灰度图格式
    result = cv2.bitwise_not(cleaned)
    return result


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    """增强对比度

    使用 CLAHE（限制对比度自适应直方图均衡化）增强字符与背景的对比度

    Args:
        gray: 灰度图

    Returns:
        增强后的灰度图
    """
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return enhanced


def preprocess_page(image_path: str, output_path: str = None,
                    remove_lines: bool = True) -> np.ndarray:
    """完整的页面预处理流程

    Args:
        image_path: 输入图片路径
        output_path: 输出图片路径（可选）
        remove_lines: 是否去除网格线

    Returns:
        预处理后的灰度图
    """
    # 1. 加载图片
    gray = load_image(image_path)
    print(f"[预处理] 加载图片: {gray.shape}")

    # 2. 裁剪内容区域
    y_min, y_max, x_min, x_max = detect_content_bbox(gray)
    gray = gray[y_min:y_max, x_min:x_max]
    print(f"[预处理] 裁剪内容区域: ({x_min},{y_min}) -> ({x_max},{y_max})")

    # 3. 去除网格线
    if remove_lines:
        gray = remove_grid_lines(gray)
        print("[预处理] 已去除网格线")

    # 4. 增强对比度
    gray = enhance_contrast(gray)
    print("[预处理] 已增强对比度")

    # 5. 保存结果
    if output_path:
        cv2.imwrite(output_path, gray)
        print(f"[预处理] 保存结果: {output_path}")

    return gray
