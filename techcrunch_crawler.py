"""
TechCrunch文章爬虫
支持爬取文章列表和完整内容，可上传到Supabase数据库
"""
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class TechCrunchCrawler:
    """TechCrunch文章爬虫，支持文章列表和内容提取，可上传到Supabase"""
    
    def __init__(self, supabase_config: Dict = None):
        self.base_url = "https://techcrunch.com"
        self.latest_url = "https://techcrunch.com/latest/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.articles = []
        
        # Supabase配置
        self.supabase_client = None
        self.supabase_config = supabase_config
        if supabase_config and SUPABASE_AVAILABLE:
            self._init_supabase(supabase_config)
    
    def _init_supabase(self, config: Dict):
        """初始化Supabase客户端"""
        try:
            self.supabase_client = create_client(
                config['url'], 
                config['anon_key']
            )
            logging.info("Supabase客户端初始化成功")
        except Exception as e:
            logging.error(f"Supabase初始化失败: {e}")
            self.supabase_client = None
    
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
            """获取字符n-gram集合"""
            if len(text) < n:
                return {text}
            return set(text[i:i+n] for i in range(len(text)-n+1))
        
        # 使用3-gram计算相似度
        ngrams1 = get_char_ngrams(text1, 3)
        ngrams2 = get_char_ngrams(text2, 3)
        
        if not ngrams1 or not ngrams2:
            return False
        
        # 计算Jaccard相似度
        intersection = len(ngrams1.intersection(ngrams2))
        union = len(ngrams1.union(ngrams2))
        
        if union == 0:
            return False
        
        similarity = intersection / union
        
        # 记录相似度用于调试
        if similarity > 0.7:  # 只记录较高相似度的比较
            logging.debug(f"文本相似度: {similarity:.3f} (阈值: {threshold})")
        
        return similarity >= threshold
    
    def upload_to_supabase(self, articles: List[Dict] = None) -> bool:
        """将文章上传到Supabase数据库"""
        if not self.supabase_client:
            logging.warning("Supabase客户端未初始化，跳过上传")
            return False
        
        if articles is None:
            articles = self.articles
        
        if not articles:
            logging.warning("没有文章数据需要上传")
            return False
        
        # 过滤只有内容的文章
        articles_with_content = [a for a in articles if a.get('content')]
        if not articles_with_content:
            logging.warning("没有包含内容的文章，跳过上传")
            return False
        
        try:
            # 准备数据
            upload_data = []
            for article in articles_with_content:
                # 解析发布时间
                published_at = article.get('published_time', '')
                if published_at:
                    try:
                        # 转换为ISO格式
                        dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        published_at = dt.isoformat()
                    except:
                        published_at = datetime.now().isoformat()
                else:
                    published_at = datetime.now().isoformat()
                
                data = {
                    'title': article.get('title', ''),
                    'source': 'TechCrunch',
                    'published_at': published_at,
                    'content': article.get('content', ''),
                    'url': article.get('url', '')
                }
                upload_data.append(data)
            
            # 批量上传 - 先检查重复文章
            table_name = self.supabase_config.get('table_name', 'news_items')
            
            # 获取现有文章的URL和内容前缀进行去重
            existing_urls = set()
            existing_content_prefixes = set()
            try:
                existing_result = self.supabase_client.table(table_name).select("url, content").execute()
                existing_urls = {item['url'] for item in existing_result.data}
                
                # 提取现有文章内容的前300个字符用于比较
                for item in existing_result.data:
                    content = item.get('content', '')
                    if content:
                        # 清理并标准化前300个字符
                        prefix = content[:300].lower().strip()
                        # 移除多余空白字符
                        prefix = ' '.join(prefix.split())
                        if len(prefix) > 50:  # 只保存足够长的前缀
                            existing_content_prefixes.add(prefix)
                
                logging.info(f"数据库中已有 {len(existing_urls)} 篇文章")
                logging.info(f"收集了 {len(existing_content_prefixes)} 个内容前缀用于去重")
            except Exception as e:
                logging.warning(f"无法获取现有文章列表: {e}")
            
            # 获取现有文章的标题进行精确去重
            existing_titles = set()
            try:
                title_result = self.supabase_client.table(table_name).select("title").execute()
                existing_titles = {item['title'] for item in title_result.data}
                logging.debug(f"获取到 {len(existing_titles)} 个现有标题用于去重")
            except Exception as e:
                logging.warning(f"无法获取现有标题列表: {e}")
            
            # 智能过滤重复文章
            new_articles = []
            duplicate_count = 0
            
            for article in upload_data:
                article_title = article.get('title', '')
                
                # 1. 标题完全匹配检查（最可靠）
                if article_title and article_title in existing_titles:
                    duplicate_count += 1
                    logging.debug(f"跳过标题重复文章: {article_title}")
                    continue
                
                # 2. URL完全匹配检查
                if article['url'] in existing_urls:
                    duplicate_count += 1
                    logging.debug(f"跳过URL重复文章: {article.get('title', 'N/A')}")
                    continue
                
                # 3. 内容相似性检查
                content = article.get('content', '')
                if content:
                    # 获取当前文章的前300个字符
                    current_prefix = content[:300].lower().strip()
                    current_prefix = ' '.join(current_prefix.split())
                    
                    if len(current_prefix) > 50:
                        # 检查是否与现有内容前缀相似
                        is_duplicate = False
                        for existing_prefix in existing_content_prefixes:
                            # 计算相似度
                            if self._is_text_similar(current_prefix, existing_prefix):
                                duplicate_count += 1
                                logging.debug(f"发现内容相似的重复文章: {article.get('title', 'N/A')}")
                                is_duplicate = True
                                break
                        
                        if is_duplicate:
                            continue
                        
                        # 添加到现有前缀集合，防止本批次内重复
                        existing_content_prefixes.add(current_prefix)
                
                # 添加标题到集合，防止本批次内重复
                if article_title:
                    existing_titles.add(article_title)
                
                new_articles.append(article)
            
            if duplicate_count > 0:
                logging.info(f"过滤了 {duplicate_count} 篇重复文章")
            
            if not new_articles:
                logging.info("没有新文章需要上传")
                return True
            
            logging.info(f"过滤后有 {len(new_articles)} 篇新文章需要上传")
            
            # 使用单条插入策略避免批量插入时的唯一约束冲突
            successful_uploads = 0
            failed_uploads = 0
            
            for i, article in enumerate(new_articles, 1):
                max_retries = 3
                retry_count = 0
                uploaded = False
                
                while retry_count < max_retries and not uploaded:
                    try:
                        # 尝试单条插入，优先使用 insert，失败时自动降级到 upsert
                        if retry_count == 0:
                            # 第一次尝试：普通插入
                            result = self.supabase_client.table(table_name).insert(article).execute()
                        else:
                            # 重试时使用 upsert 避免冲突
                            result = self.supabase_client.table(table_name).upsert(
                                article,
                                on_conflict='title'
                            ).execute()
                        
                        successful_uploads += 1
                        uploaded = True
                        if retry_count > 0:
                            logging.info(f"重试成功上传文章: {article.get('title', 'N/A')}")
                        
                    except Exception as e:
                        error_msg = str(e).lower()
                        retry_count += 1
                        
                        if 'duplicate key' in error_msg or '23505' in error_msg:
                            if retry_count < max_retries:
                                logging.debug(f"检测到重复，尝试upsert: {article.get('title', 'N/A')}")
                                time.sleep(0.5)  # 短暂延迟后重试
                                continue
                            else:
                                logging.debug(f"跳过重复文章: {article.get('title', 'N/A')}")
                                break
                        elif 'network' in error_msg or 'timeout' in error_msg or 'connection' in error_msg:
                            if retry_count < max_retries:
                                logging.warning(f"网络错误，{retry_count}/{max_retries} 次重试: {article.get('title', 'N/A')}")
                                time.sleep(1 * retry_count)  # 递增延迟
                                continue
                            else:
                                logging.error(f"网络错误多次重试失败: {article.get('title', 'N/A')}")
                                break
                        else:
                            logging.warning(f"上传文章失败 ({retry_count}/{max_retries}): {article.get('title', 'N/A')}, 错误: {e}")
                            if retry_count < max_retries:
                                time.sleep(0.5 * retry_count)
                                continue
                            break
                
                if not uploaded:
                    failed_uploads += 1
                
                # 显示进度
                if i % 5 == 0 or i == len(new_articles):
                    logging.info(f"上传进度: {i}/{len(new_articles)}, 成功: {successful_uploads}, 失败: {failed_uploads}")
            
            logging.info(f"上传结果: 成功 {successful_uploads} 篇，跳过/失败 {failed_uploads} 篇")
            return successful_uploads > 0
            
        except Exception as e:
            logging.error(f"上传到Supabase失败: {e}")
            return False
        
    def fetch_page(self, url: str, max_retries: int = 3) -> Optional[str]:
        """获取页面HTML内容"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logging.error(f"获取页面失败 ({url}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        return None
    
    def get_article_list(self, pages: int = 1, early_stop_hours: int = None) -> List[Dict]:
        """获取文章列表"""
        articles = []
        seen_urls = set()  # 用于去重
        cutoff_time = None
        
        # 如果设置了早期停止，计算截止时间
        if early_stop_hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=early_stop_hours)
            logging.info(f"启用早期停止机制：只爬取{early_stop_hours}小时内的文章")
        
        for page in range(1, pages + 1):
            if page == 1:
                url = self.latest_url
            else:
                url = f"{self.latest_url}page/{page}/"
            
            logging.info(f"正在获取第 {page} 页文章列表...")
            
            html = self.fetch_page(url)
            if not html:
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 查找文章元素
            post_elements = soup.find_all('li', class_='wp-block-post')
            
            for post_elem in post_elements:
                try:
                    article = {}
                    
                    # 提取标题和链接
                    title_link = post_elem.select_one('a[href*="techcrunch.com/20"]')
                    if title_link:
                        article['title'] = title_link.get_text(strip=True)
                        article['url'] = title_link.get('href')
                    
                    # 提取作者
                    author_link = post_elem.select_one('a[href*="/author/"]')
                    if author_link:
                        article['author'] = author_link.get_text(strip=True)
                        article['author_url'] = author_link.get('href')
                    
                    # 提取时间
                    time_elem = post_elem.find('time')
                    if time_elem:
                        article['published_time'] = time_elem.get('datetime', '')
                        article['relative_time'] = time_elem.get_text(strip=True)
                    
                    # 提取分类
                    category_link = post_elem.select_one('a[href*="/category/"]')
                    if category_link:
                        article['category'] = category_link.get_text(strip=True)
                    
                    # 提取图片
                    img_elem = post_elem.find('img')
                    if img_elem:
                        article['image_url'] = img_elem.get('src', '')
                    
                    # 提取文章ID
                    classes = post_elem.get('class', [])
                    for cls in classes:
                        if cls.startswith('post-') and cls[5:].isdigit():
                            article['post_id'] = cls[5:]
                            break
                    
                    if article.get('title') and article.get('url'):
                        url = article['url']
                        
                        # 去重检查
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        
                        # 早期时间过滤
                        if cutoff_time and article.get('published_time'):
                            try:
                                published_time = article.get('published_time', '')
                                if published_time.endswith('-07:00') or published_time.endswith('-08:00'):
                                    article_time = datetime.fromisoformat(published_time)
                                else:
                                    article_time = datetime.fromisoformat(published_time.replace('Z', '+00:00'))
                                
                                # 转换为UTC
                                if article_time.tzinfo is None:
                                    article_time = article_time.replace(tzinfo=timezone.utc)
                                elif article_time.tzinfo != timezone.utc:
                                    article_time = article_time.astimezone(timezone.utc)
                                
                                # 如果文章太旧，停止当前页面的处理
                                if article_time < cutoff_time:
                                    logging.info(f"遇到超过{early_stop_hours}小时的文章，停止爬取: {article.get('title', 'N/A')}")
                                    return articles  # 早期退出
                                    
                            except Exception as e:
                                logging.warning(f"解析文章时间失败: {published_time}, 错误: {e}")
                        
                        article['scraped_at'] = datetime.now().isoformat()
                        articles.append(article)
                        
                except Exception as e:
                    logging.debug(f"解析文章失败: {e}")
                    continue
            
            logging.info(f"第 {page} 页获取了 {len([a for a in post_elements if a])} 篇文章")
            
            if page < pages:
                time.sleep(2)
        
        return articles
    
    def extract_article_content(self, article_url: str) -> str:
        """提取单篇文章的完整内容"""
        html = self.fetch_page(article_url)
        if not html:
            return ""
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 尝试多种内容选择器
        content_selectors = [
            '.wp-block-post-content',
            '.entry-content',
            '.article-content',
            'main .wp-block-group'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 移除不需要的元素
                for unwanted in content_elem(['script', 'style', 'nav', 'aside', 'footer', 'header']):
                    unwanted.decompose()
                
                # 移除广告和相关内容
                for ad_elem in content_elem.select('[class*="ad"], [class*="promo"], [class*="related"]'):
                    ad_elem.decompose()
                
                # 获取纯文本
                content = content_elem.get_text(separator='\n', strip=True)
                if len(content) > 100:  # 确保内容足够长
                    return content
        
        return ""
    
    def crawl_articles(self, pages: int = 1, extract_content: bool = False, 
                      max_articles: int = None, max_workers: int = 3, early_stop_hours: int = None) -> List[Dict]:
        """
        爬取文章
        
        Args:
            pages: 爬取页数
            extract_content: 是否提取文章内容
            max_articles: 最大文章数限制
            max_workers: 并发线程数
            early_stop_hours: 早期停止时间（小时），超过此时间的文章将停止爬取
        """
        # 获取文章列表
        articles = self.get_article_list(pages, early_stop_hours)
        
        if max_articles:
            articles = articles[:max_articles]
        
        if not extract_content:
            self.articles = articles
            return articles
        
        # 提取文章内容
        print(f"找到 {len(articles)} 篇文章，开始提取内容...")
        
        def process_article(article):
            content = self.extract_article_content(article['url'])
            article['content'] = content
            article['content_length'] = len(content)
            article['has_content'] = len(content) > 0
            return article
        
        enhanced_articles = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_article, article) for article in articles]
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    enhanced_articles.append(result)
                    if i % 5 == 0:
                        print(f"已处理 {i}/{len(articles)} 篇文章")
                except Exception as e:
                    logging.error(f"处理文章失败: {e}")
        
        # 按原顺序排序
        enhanced_articles.sort(key=lambda x: articles.index(next(a for a in articles if a['url'] == x['url'])))
        
        self.articles = enhanced_articles
        return enhanced_articles
    
    def save_to_json(self, filename: str = None) -> str:
        """保存为JSON格式"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            has_content = any(a.get('has_content') for a in self.articles)
            prefix = "techcrunch_with_content" if has_content else "techcrunch_articles"
            filename = f"{prefix}_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.articles, f, ensure_ascii=False, indent=2)
            
            print(f"已保存到 {filename}")
            return filename
        except Exception as e:
            print(f"保存JSON文件失败: {e}")
            return None
    
    def save_to_csv(self, filename: str = None) -> str:
        """保存为CSV格式"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"techcrunch_articles_{timestamp}.csv"
        
        try:
            import csv
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                if not self.articles:
                    return None
                
                # 基础字段
                fieldnames = ['title', 'url', 'author', 'published_time', 'relative_time', 'category']
                
                # 如果有内容，添加内容相关字段
                if any(a.get('has_content') for a in self.articles):
                    fieldnames.extend(['content_length', 'has_content'])
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for article in self.articles:
                    row = {field: article.get(field, '') for field in fieldnames}
                    writer.writerow(row)
            
            print(f"已保存到 {filename}")
            return filename
        except Exception as e:
            print(f"保存CSV文件失败: {e}")
            return None
    
    def save_content_text(self, filename: str = None) -> str:
        """保存文章内容为可读文本格式"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"techcrunch_content_{timestamp}.txt"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                content_articles = [a for a in self.articles if a.get('content')]
                
                if not content_articles:
                    f.write("没有文章包含内容\n")
                    return filename
                
                for i, article in enumerate(content_articles, 1):
                    f.write("=" * 80 + "\n")
                    f.write(f"文章 {i}: {article.get('title', 'N/A')}\n")
                    f.write(f"作者: {article.get('author', 'N/A')}\n")
                    f.write(f"时间: {article.get('relative_time', 'N/A')}\n")
                    f.write(f"分类: {article.get('category', 'N/A')}\n")
                    f.write(f"链接: {article.get('url', 'N/A')}\n")
                    f.write(f"内容长度: {article.get('content_length', 0)} 字符\n")
                    f.write("=" * 80 + "\n\n")
                    f.write(article['content'])
                    f.write("\n\n" + "=" * 80 + "\n\n")
            
            print(f"已保存文章内容到 {filename}")
            return filename
        except Exception as e:
            print(f"保存文本文件失败: {e}")
            return None
    
    def print_summary(self):
        """打印爬取摘要"""
        if not self.articles:
            print("没有文章数据")
            return
        
        total = len(self.articles)
        with_content = sum(1 for a in self.articles if a.get('has_content'))
        
        print(f"\n=== 爬取摘要 ===")
        print(f"总文章数: {total}")
        
        if with_content > 0:
            print(f"包含内容的文章: {with_content}")
            print(f"内容提取成功率: {with_content/total*100:.1f}%")
            avg_length = sum(a.get('content_length', 0) for a in self.articles if a.get('has_content')) / with_content
            print(f"平均内容长度: {avg_length:.0f} 字符")
        
        # 统计作者
        authors = {}
        categories = {}
        for article in self.articles:
            author = article.get('author', 'Unknown')
            category = article.get('category', 'Unknown')
            authors[author] = authors.get(author, 0) + 1
            categories[category] = categories.get(category, 0) + 1
        
        print(f"\n作者统计 (前5名):")
        for author, count in sorted(authors.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {author}: {count} 篇")
        
        print(f"\n分类统计 (前5名):")
        for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {category}: {count} 篇")
        
        print(f"\n最新文章预览:")
        for i, article in enumerate(self.articles[:5], 1):
            title = article.get('title', 'N/A')
            if len(title) > 60:
                title = title[:60] + "..."
            content_status = "[有内容]" if article.get('has_content') else "[仅标题]"
            print(f"  {i}. {content_status} {title}")


def load_config():
    """加载配置文件"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config.get('supabase') if config.get('supabase', {}).get('enabled', False) else None
    except FileNotFoundError:
        logging.warning("未找到config.json配置文件，将使用默认配置")
        return None
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
        return None

def main():
    """主函数 - 演示不同的使用方式"""
    print("TechCrunch 爬虫")
    print("=" * 50)
    
    # 加载Supabase配置
    supabase_config = load_config()
    if supabase_config:
        print("[√] Supabase配置已加载")
    else:
        print("[!] 未配置Supabase，将只能保存到本地文件")
    
    crawler = TechCrunchCrawler(supabase_config)
    
    print("\n选择爬取模式:")
    print("1. 仅爬取文章列表（快速）")
    print("2. 爬取文章列表 + 完整内容（较慢但完整）")
    print("3. 爬取单篇文章内容")
    print("4. 爬取完整内容并上传到Supabase（推荐）")
    
    try:
        choice = input("\n请选择模式 (1/2/3/4，默认为4): ").strip()
        
        if choice == "1":
            # 仅爬取文章列表
            print("\n开始爬取文章列表...")
            articles = crawler.crawl_articles(pages=3, extract_content=False)
            
            if articles:
                crawler.print_summary()
                crawler.save_to_json()
                crawler.save_to_csv()
            
        elif choice == "3":
            # 单篇文章
            url = input("\n请输入文章URL: ").strip()
            if url:
                print("正在提取文章内容...")
                content = crawler.extract_article_content(url)
                if content:
                    print(f"\n成功提取内容，长度: {len(content)} 字符")
                    print(f"\n前200字符预览:\n{content[:200]}...")
                else:
                    print("无法提取文章内容")
        
        elif choice == "4":
            # 爬取完整内容并上传到Supabase（新增）
            pages = int(input("请输入要爬取的页数 (默认2页): ") or "2")
            max_articles = input("请输入最大文章数限制 (回车表示无限制): ").strip()
            max_articles = int(max_articles) if max_articles else None
            
            print(f"\n开始爬取 {pages} 页文章（包含完整内容）...")
            articles = crawler.crawl_articles(
                pages=pages, 
                extract_content=True, 
                max_articles=max_articles,
                max_workers=3
            )
            
            if articles:
                crawler.print_summary()
                
                # 上传到Supabase
                print("\n正在上传到Supabase数据库...")
                if crawler.upload_to_supabase():
                    print("[√] 上传成功！")
                else:
                    print("[×] 上传失败，请检查Supabase配置")
                
                # 保存本地文件
                crawler.save_to_json()
                crawler.save_to_csv()
                crawler.save_content_text()
        
        else:
            # 爬取完整内容（模式2，默认）
            pages = int(input("请输入要爬取的页数 (默认2页): ") or "2")
            max_articles = input("请输入最大文章数限制 (回车表示无限制): ").strip()
            max_articles = int(max_articles) if max_articles else None
            
            print(f"\n开始爬取 {pages} 页文章（包含完整内容）...")
            articles = crawler.crawl_articles(
                pages=pages, 
                extract_content=True, 
                max_articles=max_articles,
                max_workers=3
            )
            
            if articles:
                crawler.print_summary()
                crawler.save_to_json()
                crawler.save_to_csv()
                crawler.save_content_text()
            
    except KeyboardInterrupt:
        print("\n用户取消操作")
    except Exception as e:
        print(f"\n运行出错: {e}")


if __name__ == "__main__":
    main()