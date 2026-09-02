# EQ Children — Data Collector

儿童情绪智力（EQ）资源数据采集项目，为推荐系统提供数据基础。

收集了两类资源：**儿童 SEL 书籍** 和 **YouTube SEL 视频**，均按 CASEL 五大核心能力分类，支持按年龄、受众、情绪标签过滤。

---

## 数据概览

| 数据集 | 记录数 | 存储位置 |
|--------|--------|----------|
| 儿童 SEL 书籍 | 365 条 | Supabase `books` 表 |
| YouTube SEL 视频 | 2,427 条 | Supabase `videos` 表 |

---

## 项目结构

```
data-collector/
├── data/
│   └── raw/
│       ├── eq_children_books_v2.csv      # 书籍原始数据（365条）
│       ├── eq_children_books_v3.csv      # 书籍 + Goodreads 评分
│       ├── eq_children_youtube_v2.csv    # YouTube 视频原始数据（2427条）
│       ├── fetch_youtube_sel.py          # YouTube API 采集脚本
│       ├── enrich_books.py               # 书籍数据丰富化（Google Books）
│       ├── enrich_goodreads.py           # 书籍 Goodreads 评分抓取
│       └── import_videos_to_supabase.py  # 视频导入 Supabase
├── notebooks/                            # 分析笔记本
├── reports/                              # 报告输出
└── requirements.txt
```

---

## 数据字段

### 书籍（books 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| title | text | 书名 |
| author | text | 作者 |
| age_min / age_max | int | 适读年龄范围 |
| book_type | text | children_fiction / children_nonfiction / parenting |
| audience | text[] | children / educators / parents |
| casel_domain | text | CASEL 五大核心能力之一 |
| problem_tags | text[] | 情绪/问题标签，用于推荐匹配 |
| google_rating | numeric | Google Books 评分 |
| goodreads_rating | numeric | Goodreads 评分 |
| cover_url | text | 封面图 URL |
| amazon_url | text | Amazon 购买链接 |

### 视频（videos 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| title | text | 视频标题 |
| channel_name | text | 频道名 |
| youtube_url | text | YouTube 链接 |
| video_id | text | YouTube 视频 ID（唯一键） |
| category | text | children_video / read_aloud / sel_course / parent_guide |
| casel_domain | text | CASEL 五大核心能力之一 |
| problem_tags | text[] | 情绪/问题标签 |
| age_min / age_max | int | 适合年龄范围 |
| audience | text[] | children / educators / parents |
| view_count | bigint | 播放量 |
| like_count | bigint | 点赞数 |
| duration | text | 时长（如 "3:25"） |
| thumbnail_url | text | 缩略图 URL |
| low_quality_flag | bool | 发布>1年且播放<500且0点赞，标记为低质量 |

---

## CASEL 五大核心能力

- **Self-Awareness**（自我认知）：情绪识别、自信、身份认同
- **Self-Management**（自我管理）：情绪调节、正念、坚韧
- **Social-Awareness**（社会认知）：共情、多样性、包容
- **Relationship-Skills**（关系技能）：友谊、冲突解决、团队合作
- **Responsible-Decision-Making**（负责任决策）：后果意识、数字公民素养

---

## 复现步骤

### 1. 采集 YouTube 视频

```bash
# 需要 YouTube Data API v3 密钥
YOUTUBE_API_KEY=your_key python3 data/raw/fetch_youtube_sel.py
# 输出: data/raw/eq_children_youtube_v2.csv
# 配额消耗: ~5,858 / 10,000 units（55 个查询 × 101 units）
```

### 2. 导入 Supabase

```bash
# 先在 Supabase SQL Editor 运行 schema 文件建表
# 再运行导入脚本
SUPABASE_URL=https://xxxx.supabase.co \
SUPABASE_KEY=your_service_role_key \
python3 data/raw/import_videos_to_supabase.py
```

### 3. 环境变量

```bash
cp .env.example .env
# 填写:
# YOUTUBE_API_KEY=
# SUPABASE_URL=
# SUPABASE_KEY=
```

---

## 数据质量说明

- YouTube 视频来自 55 个 SEL 相关搜索词，已去重
- 标签（problem_tags / casel_domain）由规则匹配 + LLM 辅助标注
- `low_quality_flag=true` 的视频仍保留在库中，前端可选择是否展示
- 视频覆盖英语为主，含少量西班牙语内容（标有 `spanish` tag）

