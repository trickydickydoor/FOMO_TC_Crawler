#!/usr/bin/env python3
"""
TechCrunch自动化爬虫
专为GitHub Actions设计，支持24小时内文章过滤
"""
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from techcrunch_crawler import TechCrunchCrawler, load_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def filter_recent_articles(articles, hours=24):
    """过滤最近N小时内的文章"""
    if not articles:
        return []
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered_articles = []
    
    for article in articles:
        published_time = article.get('published_time', '')
        if not published_time:
            # 如果没有时间信息，保留文章
            filtered_articles.append(article)
            continue
        
        try:
            # 解析时间
            if published_time.endswith('-07:00') or published_time.endswith('-08:00'):
                # TechCrunch使用PT时区
                article_time = datetime.fromisoformat(published_time)
            else:
                article_time = datetime.fromisoformat(published_time.replace('Z', '+00:00'))
            
            # 转换为UTC进行比较
            if article_time.tzinfo is None:
                article_time = article_time.replace(tzinfo=timezone.utc)
            elif article_time.tzinfo != timezone.utc:
                article_time = article_time.astimezone(timezone.utc)
            
            if article_time >= cutoff_time:
                filtered_articles.append(article)
                
        except Exception as e:
            logging.warning(f"解析文章时间失败: {published_time}, 错误: {e}")
            # 时间解析失败，保留文章
            filtered_articles.append(article)
    
    return filtered_articles

def main():
    """主函数"""
    try:
        # 获取环境变量
        hours = int(os.getenv('HOURS', '24'))
        
        logging.info("=== TechCrunch 自动化爬虫启动 ===")
        logging.info(f"配置: 时间限制={hours}小时")
        
        # 加载配置
        config = load_config()
        if not config:
            logging.error("未找到Supabase配置，无法继续运行")
            sys.exit(1)
        
        logging.info("Supabase配置加载成功")
        
        # 创建爬虫实例
        crawler = TechCrunchCrawler(config)
        if not crawler.supabase_client:
            logging.error("Supabase客户端初始化失败")
            sys.exit(1)
        
        # 爬取文章（基于时间限制，无页数和文章数限制）
        logging.info(f"开始爬取文章（时间限制: {hours}小时）...")
        articles = crawler.crawl_articles(
            pages=999,  # 设置足够大的页数
            extract_content=True,
            max_articles=None,  # 不限制文章数
            max_workers=3,
            early_stop_hours=hours  # 使用环境变量的时间限制
        )
        
        if not articles:
            logging.warning("没有爬取到任何文章")
            return
        
        logging.info(f"成功爬取 {len(articles)} 篇文章（{hours}小时内）")
        
        # 只上传有内容的文章
        articles_with_content = [a for a in articles if a.get('content') and len(a.get('content', '')) > 100]
        logging.info(f"其中 {len(articles_with_content)} 篇文章包含有效内容")
        
        if not articles_with_content:
            logging.info("没有包含有效内容的文章，结束运行")
            return
        
        # 上传到Supabase
        logging.info("开始上传到Supabase数据库...")
        crawler.articles = articles_with_content  # 更新爬虫实例的文章列表
        
        if crawler.upload_to_supabase():
            logging.info(f"✅ 成功上传 {len(articles_with_content)} 篇文章到数据库")
            
            # 保存备份文件（仅在成功上传后）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"backup_articles_{timestamp}.json"
            crawler.save_to_json(backup_file)
            logging.info(f"备份文件已保存: {backup_file}")
            
        else:
            logging.error("❌ 上传失败")
            sys.exit(1)
        
        # 打印统计信息
        crawler.print_summary()
        
        logging.info("=== 自动化爬虫运行完成 ===")
        
    except KeyboardInterrupt:
        logging.info("用户中断操作")
        sys.exit(0)
    except Exception as e:
        logging.error(f"运行出错: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()