#!/usr/bin/env python3
"""
Supabase数据库去重脚本
用于清理现有数据库中的重复文章
"""
import json
import logging
from datetime import datetime
from typing import List, Dict, Set, Tuple
from techcrunch_crawler import TechCrunchCrawler, load_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DatabaseDeduplicator:
    def __init__(self, supabase_config: Dict):
        self.supabase_config = supabase_config
        self.crawler = TechCrunchCrawler(supabase_config)
        if not self.crawler.supabase_client:
            raise Exception("Supabase客户端初始化失败")
        
        self.table_name = supabase_config.get('table_name', 'news_items')
        
    def _is_text_similar(self, text1: str, text2: str, threshold: float = 0.85) -> bool:
        """检查两段文本是否相似（基于字符级相似度）"""
        if not text1 or not text2:
            return False
        
        # 如果文本完全相同
        if text1 == text2:
            return True
        
        # 如果长度差异太大，认为不相似
        len_diff = abs(len(text1) - len(text2))
        max_len = max(len(text1), len(text2))
        if max_len > 0 and len_diff / max_len > 0.3:
            return False
        
        # 使用字符级别的n-gram计算相似度
        def get_char_ngrams(text, n=3):
            if len(text) < n:
                return {text}
            return set(text[i:i+n] for i in range(len(text)-n+1))
        
        ngrams1 = get_char_ngrams(text1, 3)
        ngrams2 = get_char_ngrams(text2, 3)
        
        if not ngrams1 or not ngrams2:
            return False
        
        intersection = len(ngrams1.intersection(ngrams2))
        union = len(ngrams1.union(ngrams2))
        
        if union == 0:
            return False
        
        similarity = intersection / union
        return similarity >= threshold
    
    def get_all_articles(self) -> List[Dict]:
        """获取数据库中所有文章"""
        try:
            logging.info("正在获取数据库中的所有文章...")
            result = self.crawler.supabase_client.table(self.table_name).select("*").execute()
            articles = result.data
            logging.info(f"获取到 {len(articles)} 篇文章")
            return articles
        except Exception as e:
            logging.error(f"获取文章失败: {e}")
            return []
    
    def find_duplicates(self, articles: List[Dict]) -> List[Tuple[Dict, List[Dict]]]:
        """
        查找重复文章
        返回格式: [(保留的文章, [重复文章列表]), ...]
        """
        logging.info("开始查找重复文章...")
        
        duplicates = []
        processed_ids = set()
        
        for i, article in enumerate(articles):
            if article['id'] in processed_ids:
                continue
            
            article_id = article['id']
            title = article.get('title', '')
            content = article.get('content', '')
            url = article.get('url', '')
            
            # 提取内容前缀用于比较
            content_prefix = ""
            if content:
                content_prefix = content[:300].lower().strip()
                content_prefix = ' '.join(content_prefix.split())
            
            # 查找相似文章
            similar_articles = []
            
            for j, other_article in enumerate(articles[i+1:], i+1):
                if other_article['id'] in processed_ids:
                    continue
                
                other_title = other_article.get('title', '')
                other_content = other_article.get('content', '')
                other_url = other_article.get('url', '')
                
                is_duplicate = False
                duplicate_reason = ""
                
                # 1. URL完全匹配
                if url and other_url and url == other_url:
                    is_duplicate = True
                    duplicate_reason = "URL相同"
                
                # 2. 内容前缀相似性检查
                elif content and other_content:
                    other_content_prefix = other_content[:300].lower().strip()
                    other_content_prefix = ' '.join(other_content_prefix.split())
                    
                    if len(content_prefix) > 50 and len(other_content_prefix) > 50:
                        if self._is_text_similar(content_prefix, other_content_prefix):
                            is_duplicate = True
                            duplicate_reason = "内容相似"
                
                if is_duplicate:
                    similar_articles.append({
                        'article': other_article,
                        'reason': duplicate_reason
                    })
                    processed_ids.add(other_article['id'])
                    logging.info(f"发现重复: '{title}' vs '{other_title}' ({duplicate_reason})")
            
            if similar_articles:
                duplicates.append((article, similar_articles))
                processed_ids.add(article_id)
        
        logging.info(f"找到 {len(duplicates)} 组重复文章")
        return duplicates
    
    def preview_duplicates(self, duplicates: List[Tuple[Dict, List[Dict]]]):
        """预览要删除的重复文章"""
        if not duplicates:
            logging.info("没有发现重复文章")
            return
        
        total_to_delete = 0
        print("\n" + "="*80)
        print("重复文章预览")
        print("="*80)
        
        for i, (keep_article, duplicate_list) in enumerate(duplicates, 1):
            print(f"\n【第{i}组重复】")
            print(f"保留: {keep_article.get('title', 'N/A')}")
            print(f"     ID: {keep_article['id']}")
            print(f"     发布时间: {keep_article.get('published_at', 'N/A')}")
            print(f"     URL: {keep_article.get('url', 'N/A')}")
            
            print(f"\n将删除 {len(duplicate_list)} 篇重复文章:")
            for j, dup_info in enumerate(duplicate_list, 1):
                dup_article = dup_info['article']
                reason = dup_info['reason']
                print(f"  {j}. [{reason}] {dup_article.get('title', 'N/A')}")
                print(f"     ID: {dup_article['id']} | 发布时间: {dup_article.get('published_at', 'N/A')}")
                total_to_delete += 1
        
        print(f"\n总计: 发现 {len(duplicates)} 组重复，将删除 {total_to_delete} 篇文章")
        print("="*80)
    
    def delete_duplicates(self, duplicates: List[Tuple[Dict, List[Dict]]], dry_run: bool = True) -> int:
        """删除重复文章"""
        if not duplicates:
            logging.info("没有重复文章需要删除")
            return 0
        
        to_delete_ids = []
        for keep_article, duplicate_list in duplicates:
            for dup_info in duplicate_list:
                to_delete_ids.append(dup_info['article']['id'])
        
        if dry_run:
            logging.info(f"[预演模式] 将删除 {len(to_delete_ids)} 篇重复文章")
            return len(to_delete_ids)
        
        deleted_count = 0
        
        # 分批删除
        batch_size = 10
        for i in range(0, len(to_delete_ids), batch_size):
            batch_ids = to_delete_ids[i:i + batch_size]
            
            try:
                # 使用in操作符删除多个记录
                result = self.crawler.supabase_client.table(self.table_name).delete().in_('id', batch_ids).execute()
                batch_deleted = len(batch_ids)
                deleted_count += batch_deleted
                logging.info(f"已删除批次 {i//batch_size + 1}: {batch_deleted} 篇文章")
            except Exception as e:
                logging.error(f"删除批次 {i//batch_size + 1} 失败: {e}")
        
        logging.info(f"✅ 总共删除了 {deleted_count} 篇重复文章")
        return deleted_count
    
    def create_backup(self, articles: List[Dict]) -> str:
        """创建数据备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"database_backup_{timestamp}.json"
        
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(articles, f, ensure_ascii=False, indent=2, default=str)
            
            logging.info(f"数据备份已保存: {backup_file}")
            return backup_file
        except Exception as e:
            logging.error(f"创建备份失败: {e}")
            return None

def main():
    """主函数"""
    print("Supabase 数据库去重工具")
    print("="*50)
    
    # 加载配置
    config = load_config()
    if not config:
        print("❌ 未找到Supabase配置")
        return
    
    try:
        # 初始化去重器
        deduplicator = DatabaseDeduplicator(config)
        
        # 获取所有文章
        articles = deduplicator.get_all_articles()
        if not articles:
            print("❌ 无法获取文章数据")
            return
        
        # 创建备份
        print(f"\n📦 正在创建数据备份...")
        backup_file = deduplicator.create_backup(articles)
        if not backup_file:
            print("⚠️ 备份失败，但将继续执行")
        
        # 查找重复
        duplicates = deduplicator.find_duplicates(articles)
        
        # 预览重复文章
        deduplicator.preview_duplicates(duplicates)
        
        if not duplicates:
            print("✅ 数据库中没有重复文章")
            return
        
        # 询问用户是否执行删除
        print(f"\n⚠️ 注意：此操作将永久删除重复文章！")
        if backup_file:
            print(f"📦 数据备份已保存至: {backup_file}")
        
        choice = input("\n是否执行删除操作？(y/N): ").strip().lower()
        
        if choice == 'y':
            print("🗑️ 正在删除重复文章...")
            deleted_count = deduplicator.delete_duplicates(duplicates, dry_run=False)
            print(f"✅ 删除完成！共删除 {deleted_count} 篇重复文章")
            
            # 验证结果
            remaining_articles = deduplicator.get_all_articles()
            print(f"📊 数据库现有文章数: {len(remaining_articles)}")
            
        else:
            print("❌ 用户取消操作")
            
    except Exception as e:
        logging.error(f"运行出错: {e}", exc_info=True)

if __name__ == "__main__":
    main()