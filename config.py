"""项目配置参数"""
import os

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PAGES_DIR = os.path.join(OUTPUT_DIR, "pages")
CHARACTERS_DIR = os.path.join(OUTPUT_DIR, "characters")

# PDF 渲染配置
DPI_SCALE = 2  # 渲染倍数（2x = 约 200 DPI）

# 页面预处理配置
CONTENT_MARGIN = 50  # 内容区域边距容忍度（像素）

# 单字切割配置
BINARY_THRESHOLD = 140  # 二值化阈值
MIN_CHAR_AREA = 800  # 最小字符面积（过滤小字注释）
MAX_CHAR_AREA = 80000  # 最大字符面积
MIN_CHAR_WIDTH = 30  # 最小字符宽度
MAX_CHAR_WIDTH = 400  # 最大字符宽度
MIN_CHAR_HEIGHT = 30  # 最小字符高度
MAX_CHAR_HEIGHT = 500  # 最大字符高度
MIN_ASPECT_RATIO = 0.25  # 最小宽高比
MAX_ASPECT_RATIO = 4.0  # 最大宽高比

# 网格线检测配置
GRID_LINE_MIN_LENGTH = 100  # 网格线最小长度（像素）
GRID_LINE_MAX_THICKNESS = 8  # 网格线最大粗细（像素）

# 字符间距配置
CHAR_GAP_THRESHOLD = 15  # 字符间隙阈值（像素）

# 书帖排向（vertical=竖排, horizontal=横排）
LAYOUT_DIRECTION = "vertical"

# 测试页码（从0开始）
TEST_PAGE_INDEX = 23  # 第24页

# 书法家与文本信息
CALLIGRAPHER = "吴玉生"
SOURCE_TEXT = "红楼梦"
PDF_PATH = os.path.join(
    BASE_DIR,
    "吴玉生硬笔行书红楼梦诗词 (吴玉生) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
)

# 切片存储
CROPPED_DIR = os.path.join(OUTPUT_DIR, "cropped")

# Obsidian 字库路径
OBSIDIAN_VAULT = r"D:\notebooks\Lmc\brew"
CHAR_DB_DIR = os.path.join(OBSIDIAN_VAULT, "字库")

# 多书帖配置（用于 review_server 选择不同字帖）
# 每个 profile 可以覆盖 calligrapher/source_text/pdf_path/layout_direction
# 页面级元数据覆盖存储在 page_{num}_meta.json 中
COPYBOOK_PROFILES = {
    "default": {
        "calligrapher": CALLIGRAPHER,
        "source_text": SOURCE_TEXT,
        "pdf_path": PDF_PATH,
        "layout_direction": LAYOUT_DIRECTION,
    },
}

def get_profile(name="default"):
    """获取指定 profile 的配置，回退到 default"""
    profiles = COPYBOOK_PROFILES
    if name in profiles:
        return profiles[name]
    return profiles.get("default", {})
