# GitHub Action 自动化设置指南

## 1. GitHub Secrets 配置

在你的 GitHub 仓库中设置以下 Secrets：

1. 进入 GitHub 仓库
2. 点击 `Settings` → `Secrets and variables` → `Actions`
3. 添加以下 Repository secrets：

| Name | Value | 描述 |
|------|-------|------|
| `SUPABASE_URL` | `https://your-project.supabase.co` | 你的 Supabase 项目 URL |
| `SUPABASE_ANON_KEY` | `eyJhbGciOiJ...` | 你的 Supabase 匿名密钥 |

## 2. Supabase 数据库设置

在你的 Supabase 项目中执行以下 SQL 来创建表：

```sql
-- 创建 news_items 表
CREATE TABLE news_items (
  id SERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT DEFAULT 'TechCrunch',
  published_at TIMESTAMPTZ NOT NULL,
  content TEXT NOT NULL,
  url TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 创建索引提高查询性能
CREATE INDEX idx_news_items_published_at ON news_items(published_at);
CREATE INDEX idx_news_items_source ON news_items(source);
CREATE UNIQUE INDEX idx_news_items_url ON news_items(url);

-- 启用 Row Level Security (RLS)
ALTER TABLE news_items ENABLE ROW LEVEL SECURITY;

-- 创建策略允许插入和查询
CREATE POLICY "Enable insert for service role" ON news_items
FOR INSERT WITH CHECK (true);

CREATE POLICY "Enable select for service role" ON news_items
FOR SELECT USING (true);
```

## 3. GitHub Action 工作流说明

### 自动触发
- 每小时自动运行一次（UTC 时间）
- 爬取最近 24 小时内的文章
- 自动过滤重复文章
- 仅上传包含有效内容的文章

### 手动触发
可以在 GitHub Actions 页面手动运行，支持自定义参数：
- `pages`: 爬取页数（默认 3）
- `max_articles`: 最大文章数限制（默认 50）

### 监控和日志
- 运行失败时会上传日志文件
- 所有操作都有详细的日志记录
- 可以在 Actions 页面查看运行历史

## 4. 本地开发设置

1. 复制配置模板：
```bash
cp config.template.json config.json
```

2. 编辑 `config.json` 填入你的 Supabase 配置

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 运行测试：
```bash
# 测试手动爬虫
python techcrunch_crawler.py

# 测试自动化爬虫
python automated_crawler.py
```

## 5. 故障排除

### 常见问题

1. **Supabase 连接失败**
   - 检查 URL 和 API 密钥是否正确
   - 确认 Supabase 项目处于活跃状态
   - 检查数据库表是否存在

2. **权限错误**
   - 确认使用的是 service_role 密钥
   - 检查 RLS 策略是否正确设置

3. **爬取失败**
   - 检查网络连接
   - 确认 TechCrunch 网站结构未发生变化
   - 查看详细错误日志

### 日志查看
```bash
# 查看最新日志
tail -f crawler.log

# 查看特定时间的日志
grep "2025-07-28" crawler.log
```

## 6. 定制化配置

### 修改运行频率
编辑 `.github/workflows/crawler.yml` 中的 cron 表达式：
```yaml
schedule:
  - cron: '0 */2 * * *'  # 每2小时运行一次
  - cron: '0 0 * * *'    # 每天午夜运行一次
```

### 修改文章过滤条件
编辑 `automated_crawler.py` 中的 `filter_recent_articles` 函数：
```python
# 修改时间窗口（默认24小时）
recent_articles = filter_recent_articles(articles, hours=12)  # 12小时
```

### 添加额外数据源
可以扩展爬虫支持其他科技媒体网站，只需修改 URL 和解析逻辑。