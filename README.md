# TechCrunch 自动化爬虫

一个用于爬取TechCrunch最新文章的Python爬虫工具，支持文章列表爬取、完整内容提取、Supabase数据库上传和GitHub Actions自动化运行。

## 功能特性

- 🚀 **高效爬取**: 成功爬取TechCrunch最新文章
- 📝 **内容提取**: 支持完整文章内容提取
- 💾 **多种存储**: JSON文件、CSV文件、可读文本格式
- 🗄️ **数据库上传**: 支持上传到Supabase数据库
- 🤖 **自动化运行**: GitHub Actions 每小时自动运行
- 🕒 **智能过滤**: 自动过滤24小时内的新文章
- 🔄 **错误处理**: 自动重试、异常处理
- ⚡ **并发处理**: 多线程并发提取文章内容
- 📈 **统计分析**: 文章统计、作者排行
- 🎯 **准确解析**: 基于实际HTML结构的精确解析
- ⚙️ **配置管理**: 支持配置文件管理
- 🔍 **重复检测**: 自动检测并避免重复文章

## 文件说明

### 核心文件
- `techcrunch_crawler.py` - 主爬虫程序（支持文章列表、完整内容和数据库上传）
- `automated_crawler.py` - 自动化爬虫脚本（专为GitHub Actions设计）
- `requirements.txt` - 项目依赖

### 配置文件
- `config.json` - 运行时配置文件（包含Supabase设置）
- `config.template.json` - 配置文件模板
- `.github/workflows/crawler.yml` - GitHub Actions 工作流配置

### 文档
- `README.md` - 项目说明和使用指南
- `SETUP.md` - GitHub Actions 自动化设置指南

## 安装依赖

```bash
pip install -r requirements.txt
```

## Supabase配置

如果要使用数据库上传功能，需要配置 `config.json` 文件：

```json
{
  "supabase": {
    "enabled": true,
    "url": "你的Supabase项目URL",
    "anon_key": "你的Supabase匿名密钥",
    "table_name": "news_items"
  }
}
```

### 数据库表结构

请在你的Supabase项目中创建 `news_items` 表，包含以下字段：

```sql
CREATE TABLE news_items (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT DEFAULT 'TechCrunch',
  published_at TIMESTAMPTZ NOT NULL,
  content TEXT NOT NULL,
  url TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 使用方法

### 1. 交互式使用（推荐）

直接运行主程序，会提供交互式选择：

```bash
python techcrunch_crawler.py
```

程序会提供4种模式：
1. **仅爬取文章列表**（快速）- 获取标题、作者、时间、链接等基本信息
2. **爬取完整内容**（完整）- 获取基本信息 + 文章正文内容
3. **单篇文章内容** - 提取指定URL的文章内容
4. **爬取完整内容并上传到Supabase**（推荐）- 完整爬取并自动上传到数据库

### 2. 编程方式使用

```python
from techcrunch_crawler import TechCrunchCrawler

# 方式1: 不使用Supabase
crawler = TechCrunchCrawler()

# 方式2: 使用Supabase配置
supabase_config = {
    "url": "你的Supabase项目URL",
    "anon_key": "你的Supabase匿名密钥",
    "table_name": "news_items"
}
crawler = TechCrunchCrawler(supabase_config)

# 爬取完整内容
articles = crawler.crawl_articles(
    pages=2, 
    extract_content=True, 
    max_articles=10,
    max_workers=3
)

# 保存到本地文件
crawler.save_to_json()      # JSON格式
crawler.save_to_csv()       # CSV格式  
crawler.save_content_text() # 可读文本格式

# 上传到Supabase数据库
if crawler.upload_to_supabase():
    print("上传成功！")

# 查看统计信息
crawler.print_summary()
```

## 参数说明

### crawl_articles 方法参数

- `pages` (int): 爬取页数，默认1页
- `extract_content` (bool): 是否提取文章内容，默认False
- `max_articles` (int): 最大文章数限制，默认无限制
- `max_workers` (int): 并发线程数，默认3

## 数据结构

### 基础文章信息

```json
{
  "title": "文章标题",
  "url": "文章链接", 
  "author": "作者姓名",
  "author_url": "作者链接",
  "published_time": "2025-07-27T07:39:11-07:00",
  "relative_time": "2 hours ago",
  "category": "分类",
  "image_url": "配图链接",
  "post_id": "文章ID",
  "scraped_at": "爬取时间"
}
```

### 包含内容的文章信息

在基础信息基础上，还包含：

```json
{
  "content": "完整文章正文",
  "content_length": 1500,
  "has_content": true
}
```

## 输出文件

### JSON格式
- `techcrunch_articles_*.json` - 仅包含文章列表
- `techcrunch_with_content_*.json` - 包含完整内容

### CSV格式
- `techcrunch_articles_*.csv` - 适合Excel打开的表格格式

### 文本格式
- `techcrunch_content_*.txt` - 可读的文章内容格式

## 测试结果

### 基础爬虫测试
✅ **成功测试**: 2025年7月27日，成功爬取79篇文章
- 支持多页爬取（测试了3页）
- 准确提取文章标题、作者、时间、链接等信息
- 生成JSON和CSV格式的数据文件

### 内容爬虫测试
✅ **成功测试**: 2025年7月27日，成功爬取完整文章内容
- 100%内容提取成功率
- 平均文章长度: 2000+字符
- 支持JSON、CSV和可读文本格式导出
- 并发处理提高爬取效率

### Supabase上传测试
✅ **成功测试**: 2025年7月28日，成功上传到Supabase数据库
- 自动重复文章检测
- 批量上传优化
- 完整错误处理和重试机制

## GitHub Actions 自动化

### 🚀 快速开始

1. **Fork 此仓库到你的 GitHub 账户**

2. **设置 GitHub Secrets**：
   - 进入仓库 `Settings` → `Secrets and variables` → `Actions`
   - 添加 `SUPABASE_URL` 和 `SUPABASE_ANON_KEY`

3. **设置 Supabase 数据库**：
   - 创建 `news_items` 表（见 [SETUP.md](SETUP.md)）

4. **启用 GitHub Actions**：
   - 自动每小时运行一次
   - 手动触发支持自定义参数

### 📊 自动化特性

- **定时运行**: 每小时自动爬取最新文章
- **智能时间过滤**: 只处理指定时间内的新文章（默认24小时）
- **早期停止机制**: 遇到超时文章立即停止，避免无效爬取
- **重复检测**: 自动避免重复上传相同文章
- **故障恢复**: 失败时自动保存日志和数据
- **纯时间驱动**: 无页数和文章数限制，完全基于时间控制

详细设置说明请参考 [SETUP.md](SETUP.md)

## 注意事项

1. **请求频率**: 每页之间有2秒延迟，避免对服务器造成压力
2. **User-Agent**: 使用真实浏览器User-Agent，降低被屏蔽风险
3. **错误处理**: 包含完整的错误处理和重试机制
4. **内容质量**: 自动过滤无效内容，确保提取质量

## 常见问题

**Q: 如何只爬取指定数量的文章？**
A: 使用 `max_articles` 参数限制文章数量

**Q: 爬取速度太慢怎么办？**
A: 可以调整 `max_workers` 参数增加并发数，或选择不提取内容

**Q: 如何获取更多页的文章？**
A: 增加 `pages` 参数值

**Q: 支持其他网站吗？**
A: 当前仅支持TechCrunch，其他网站需要修改解析逻辑

## 扩展开发

如需扩展功能，可以参考以下方向：

1. **其他网站**: 修改URL和解析逻辑支持其他科技媒体
2. **数据库存储**: 添加SQLite/MySQL存储支持
3. **定时爬取**: 结合cron实现定时自动爬取
4. **内容分析**: 添加关键词提取、情感分析等功能
5. **Web界面**: 开发Web界面方便非技术用户使用

## 许可证

MIT License

## 免责声明

本工具仅供学习和研究使用，请遵守网站的robots.txt和使用条款。使用时请合理控制爬取频率，避免对目标网站造成过大负担。