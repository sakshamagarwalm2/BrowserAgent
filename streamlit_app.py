import streamlit as st
import asyncio
import threading
import queue
import time
import json
import base64
from datetime import datetime
from PIL import Image
from io import BytesIO
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from openai import OpenAI
import os
from dataclasses import dataclass
from typing import List, Dict, Any

# Configure Streamlit page
st.set_page_config(
    page_title="🤖 Autonomous Browser Search Bot",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .activity-log {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 5px;
        height: 300px;
        overflow-y: auto;
        font-family: monospace;
        font-size: 12px;
    }
    .screenshot-container {
        border: 2px solid #ddd;
        border-radius: 10px;
        padding: 10px;
        background-color: white;
    }
    .result-card {
        background-color: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .status-indicator {
        padding: 0.25rem 0.5rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .status-running {
        background-color: #ffeaa7;
        color: #2d3436;
    }
    .status-complete {
        background-color: #00b894;
        color: white;
    }
    .status-error {
        background-color: #e17055;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

@dataclass
class ActivityLog:
    timestamp: str
    action_type: str
    description: str
    details: str = ""

class StreamlitBrowserSearchBot:
    def __init__(self):
        self.client = None
        self.tools = []
        self.search_results = []
        self.scraped_content = []
        self.activity_queue = queue.Queue()
        self.screenshot_queue = queue.Queue()
        self.current_status = "idle"
        
    def log_activity(self, action_type: str, description: str, details: str = ""):
        """Log activity for UI display"""
        log_entry = ActivityLog(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            action_type=action_type,
            description=description,
            details=details
        )
        self.activity_queue.put(log_entry)
        
    def initialize_openai(self, api_key: str):
        """Initialize OpenAI client with provided API key"""
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            self.client = OpenAI(api_key=api_key)
            # Test the connection with a simple request
            self.client.models.list()
            return True, "OpenAI client initialized successfully!"
        except Exception as e:
            return False, f"Failed to initialize OpenAI: {str(e)}"

    def extract_google_results(self, page):
        """Extract search results from Google search page"""
        try:
            self.log_activity("SCRAPING", "Extracting Google search results...")
            
            # Wait for search results to load
            try:
                page.wait_for_selector('div[data-sokoban-container]', timeout=10000)
            except PlaywrightTimeoutError:
                # Fallback - wait for any search result container
                try:
                    page.wait_for_selector('div.g', timeout=5000)
                except PlaywrightTimeoutError:
                    pass
            
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            results = []
            # Updated selectors for current Google layout
            search_containers = soup.select('div.g, div.tF2Cxc, div.MjjYud, div[data-sokoban-container] div.g')
            
            self.log_activity("INFO", f"Found {len(search_containers)} potential result containers")
            
            for container in search_containers[:10]:
                try:
                    # Try multiple selectors for title
                    title_element = container.select_one('h3, .LC20lb, .DKV0Md')
                    title = title_element.get_text().strip() if title_element else "No title"
                    
                    # Try multiple selectors for link
                    link_element = container.select_one('a[href]')
                    url = ""
                    if link_element:
                        url = link_element.get('href', '')
                        
                        # Clean up Google redirect URLs
                        if url.startswith('/url?'):
                            import urllib.parse
                            try:
                                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                                url = parsed.get('q', [''])[0]
                            except:
                                continue
                        elif url.startswith('/search?') or url.startswith('#'):
                            continue
                    
                    # Try multiple selectors for snippet
                    snippet_element = container.select_one('.VwiC3b, .s3v9rd, .IsZvec, .aCOpRe, .st')
                    snippet = snippet_element.get_text().strip() if snippet_element else "No description"
                    
                    # Validate result
                    if (title != "No title" and 
                        url and 
                        url.startswith('http') and 
                        len(title) > 0 and
                        not any(skip in url.lower() for skip in ['google.com', 'youtube.com/results'])):
                        
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet
                        })
                        
                except Exception as e:
                    self.log_activity("WARNING", f"Error extracting result: {str(e)}")
                    continue
            
            self.log_activity("SUCCESS", f"Extracted {len(results)} valid search results")
            return results
            
        except Exception as e:
            self.log_activity("ERROR", f"Error extracting Google results: {str(e)}")
            return []

    def scrape_webpage_content(self, url, max_chars=2000):
        """Scrape content from a webpage"""
        try:
            self.log_activity("SCRAPING", f"Scraping content from: {url[:50]}...")
            
            # Validate URL
            if not url or not url.startswith('http'):
                return f"Invalid URL: {url}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            try:
                response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                return f"Failed to fetch {url}: {str(e)}"
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for script in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
                script.decompose()
            
            # Try to find main content
            content_selectors = ['main', 'article', '.content', '#content', '.post', '.entry']
            main_content = None
            
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            # If no main content found, use body
            if not main_content:
                main_content = soup.find('body') or soup
            
            text = main_content.get_text()
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Remove extra whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            self.log_activity("SUCCESS", f"Scraped {len(text)} characters from {url[:30]}...")
            return text
            
        except Exception as e:
            error_msg = f"Error scraping {url}: {str(e)}"
            self.log_activity("ERROR", error_msg)
            return f"Could not scrape content from {url}: {str(e)}"

    def get_screenshot(self, page):
        """Take screenshot and add to queue"""
        try:
            screenshot_bytes = page.screenshot(full_page=False)
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            # Clear old screenshots and add new one
            while not self.screenshot_queue.empty():
                try:
                    self.screenshot_queue.get_nowait()
                except queue.Empty:
                    break
            
            self.screenshot_queue.put(screenshot_base64)
            return screenshot_bytes
        except Exception as e:
            self.log_activity("ERROR", f"Error taking screenshot: {str(e)}")
            return None

    def generate_summary(self, query):
        """Generate AI summary of results"""
        if not self.scraped_content:
            return "No search results found to summarize."

        self.log_activity("AI", "Generating summary with OpenAI...")
        
        content_text = f"Search Query: {query}\n\nSearch Results:\n"
        
        for i, result in enumerate(self.scraped_content, 1):
            content_text += f"\n{i}. {result['title']}\n"
            content_text += f"URL: {result['url']}\n"
            content_text += f"Snippet: {result['snippet']}\n"
            content_text += f"Content: {result['content'][:800]}...\n"  # Increased content length
            content_text += "-" * 80 + "\n"

        try:
            summary_response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Use more cost-effective model
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates concise, informative summaries of web search results. Provide a comprehensive summary that covers the key points from all the search results. Focus on the most important and relevant information."
                    },
                    {
                        "role": "user",
                        "content": f"Please provide a comprehensive summary of these search results for the query '{query}':\n\n{content_text}"
                    }
                ],
                max_tokens=1000,
                temperature=0.3
            )
            
            summary = summary_response.choices[0].message.content
            self.log_activity("SUCCESS", "AI summary generated successfully")
            return summary
            
        except Exception as e:
            error_msg = f"Error generating summary: {str(e)}"
            self.log_activity("ERROR", error_msg)
            return f"Could not generate summary due to an error: {str(e)}"

    def search_with_google(self, query, max_results=5):
        """Original Google search method (kept for compatibility)"""
        self.current_status = "running"
        self.search_results = []
        self.scraped_content = []
        
        self.log_activity("START", f"Starting Google search for: {query}")
        self.log_activity("WARNING", "Google may block automated requests with CAPTCHA")
        
        try:
            with sync_playwright() as p:
                self.log_activity("BROWSER", "Launching Chrome browser...")
                
                # Updated browser launch options
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-file-system",
                        "--disable-web-security",
                        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ]
                )

                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = context.new_page()

                self.log_activity("BROWSER", "Navigating to Google...")
                try:
                    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    page.goto("https://www.google.com", wait_until="networkidle", timeout=30000)

                # Check for CAPTCHA or unusual traffic detection
                page_content = page.content().lower()
                if "captcha" in page_content or "unusual traffic" in page_content or "not a robot" in page_content:
                    self.log_activity("ERROR", "Google detected automated traffic (CAPTCHA shown)")
                    browser.close()
                    # Fallback to DuckDuckGo
                    return self.search_with_duckduckgo(query, max_results)

                # Handle potential cookie consent
                try:
                    cookie_button = page.locator("button:has-text('Accept all'), button:has-text('I agree'), #L2AGLb")
                    if cookie_button.is_visible(timeout=3000):
                        cookie_button.click(timeout=5000)
                        self.log_activity("BROWSER", "Accepted cookie consent")
                except:
                    pass

                self.log_activity("BROWSER", f"Searching for: {query}")
                
                # More robust search input handling
                search_selectors = [
                    "textarea[name='q']",
                    "input[name='q']", 
                    "textarea[title='Search']",
                    "input[title='Search']",
                    "#APjFqb",
                    ".gLFyf"
                ]
                
                search_input = None
                for selector in search_selectors:
                    try:
                        search_input = page.locator(selector).first
                        if search_input.is_visible(timeout=5000):
                            self.log_activity("BROWSER", f"Found search input with selector: {selector}")
                            break
                    except PlaywrightTimeoutError:
                        continue
                
                if not search_input:
                    self.log_activity("ERROR", "Could not find Google search input - likely blocked")
                    browser.close()
                    return self.search_with_duckduckgo(query, max_results)
                
                # Clear any existing text and type the query
                try:
                    search_input.click(timeout=10000)
                    search_input.fill("", timeout=5000)  # Clear first
                    search_input.type(query, delay=50)  # Type with small delay
                    search_input.press("Enter", timeout=10000)
                except Exception as e:
                    self.log_activity("ERROR", f"Error during search input: {str(e)}")
                    browser.close()
                    return self.search_with_duckduckgo(query, max_results)

                # Wait for results to load
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                except PlaywrightTimeoutError:
                    self.log_activity("WARNING", "Timeout waiting for page load")

                # Check again for CAPTCHA after search
                page_content = page.content().lower()
                if "captcha" in page_content or "unusual traffic" in page_content:
                    self.log_activity("ERROR", "Google showed CAPTCHA after search")
                    browser.close()
                    return self.search_with_duckduckgo(query, max_results)

                # Take screenshot after search
                screenshot_bytes = self.get_screenshot(page)
                if screenshot_bytes:
                    self.log_activity("SCREENSHOT", "Captured search results page")

                self.log_activity("SCRAPING", "Extracting search results...")
                self.search_results = self.extract_google_results(page)

                browser.close()

                if not self.search_results:
                    self.log_activity("WARNING", "No Google results found, switching to DuckDuckGo")
                    return self.search_with_duckduckgo(query, max_results)

                self.log_activity("INFO", f"Starting to scrape {min(max_results, len(self.search_results))} results...")
                
                for i, result in enumerate(self.search_results[:max_results]):
                    try:
                        self.log_activity("PROGRESS", f"Scraping result {i+1}/{min(max_results, len(self.search_results))}: {result['title'][:50]}...")
                        content = self.scrape_webpage_content(result['url'])
                        self.scraped_content.append({
                            'title': result['title'],
                            'url': result['url'],
                            'snippet': result['snippet'],
                            'content': content
                        })
                    except Exception as e:
                        self.log_activity("WARNING", f"Failed to scrape result {i+1}: {str(e)}")
                        continue

            if not self.scraped_content:
                self.log_activity("WARNING", "No content scraped from Google, using fallback")
                return self.search_with_duckduckgo(query, max_results)

            summary = self.generate_summary(query)
            
            self.current_status = "complete"
            self.log_activity("COMPLETE", "Google search completed successfully!")
            
            return {
                'query': query,
                'search_results': self.search_results,
                'scraped_content': self.scraped_content,
                'summary': summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.current_status = "error"
            error_msg = f"Error during Google search: {str(e)}"
            self.log_activity("ERROR", error_msg)
            # Fallback to DuckDuckGo
            return self.search_with_duckduckgo(query, max_results)

    def search_with_duckduckgo(self, query, max_results=5):
        """Original Google search method (kept for compatibility)"""
        self.current_status = "running"
        self.search_results = []
        self.scraped_content = []
        
        self.log_activity("START", f"Starting Google search for: {query}")
        self.log_activity("WARNING", "Google may block automated requests with CAPTCHA")
        
        try:
            with sync_playwright() as p:
                self.log_activity("BROWSER", "Launching Chrome browser...")
                
                # Updated browser launch options
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-file-system",
                        "--disable-web-security",
                        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ]
                )

                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = context.new_page()

                self.log_activity("BROWSER", "Navigating to Google...")
                try:
                    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    page.goto("https://www.google.com", wait_until="networkidle", timeout=30000)

                # Check for CAPTCHA or unusual traffic detection
                page_content = page.content().lower()
                if "captcha" in page_content or "unusual traffic" in page_content or "not a robot" in page_content:
                    self.log_activity("ERROR", "Google detected automated traffic (CAPTCHA shown)")
                    browser.close()
                    # Fallback to DuckDuckGo
                    return self.search_with_duckduckgo(query, max_results)

                # Handle potential cookie consent
                try:
                    cookie_button = page.locator("button:has-text('Accept all'), button:has-text('I agree'), #L2AGLb")
                    if cookie_button.is_visible(timeout=3000):
                        cookie_button.click(timeout=5000)
                        self.log_activity("BROWSER", "Accepted cookie consent")
                except:
                    pass

                self.log_activity("BROWSER", f"Searching for: {query}")
                
                # More robust search input handling
                search_selectors = [
                    "textarea[name='q']",
                    "input[name='q']", 
                    "textarea[title='Search']",
                    "input[title='Search']",
                    "#APjFqb",
                    ".gLFyf"
                ]
                
                search_input = None
                for selector in search_selectors:
                    try:
                        search_input = page.locator(selector).first
                        if search_input.is_visible(timeout=5000):
                            self.log_activity("BROWSER", f"Found search input with selector: {selector}")
                            break
                    except PlaywrightTimeoutError:
                        continue
                
                if not search_input:
                    self.log_activity("ERROR", "Could not find Google search input - likely blocked")
                    browser.close()
                    return self.search_with_duckduckgo(query, max_results)
                
                # Clear any existing text and type the query
                try:
                    search_input.click(timeout=10000)
                    search_input.fill("", timeout=5000)  # Clear first
                    search_input.type(query, delay=50)  # Type with small delay
                    search_input.press("Enter", timeout=10000)
                except Exception as e:
                    self.log_activity("ERROR", f"Error during search input: {str(e)}")
                    browser.close()
                    return self.search_with_duckduckgo(query, max_results)

                # Wait for results to load
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                except PlaywrightTimeoutError:
                    self.log_activity("WARNING", "Timeout waiting for page load")

                # Check again for CAPTCHA after search
                page_content = page.content().lower()
                if "captcha" in page_content or "unusual traffic" in page_content:
                    self.log_activity("ERROR", "Google showed CAPTCHA after search")
                    browser.close()
                    return self.search_with_duckduckgo(query, max_results)

                # Take screenshot after search
                screenshot_bytes = self.get_screenshot(page)
                if screenshot_bytes:
                    self.log_activity("SCREENSHOT", "Captured search results page")

                self.log_activity("SCRAPING", "Extracting search results...")
                self.search_results = self.extract_google_results(page)

                browser.close()

                if not self.search_results:
                    self.log_activity("WARNING", "No Google results found, switching to DuckDuckGo")
                    return self.search_with_duckduckgo(query, max_results)

                self.log_activity("INFO", f"Starting to scrape {min(max_results, len(self.search_results))} results...")
                
                for i, result in enumerate(self.search_results[:max_results]):
                    try:
                        self.log_activity("PROGRESS", f"Scraping result {i+1}/{min(max_results, len(self.search_results))}: {result['title'][:50]}...")
                        content = self.scrape_webpage_content(result['url'])
                        self.scraped_content.append({
                            'title': result['title'],
                            'url': result['url'],
                            'snippet': result['snippet'],
                            'content': content
                        })
                    except Exception as e:
                        self.log_activity("WARNING", f"Failed to scrape result {i+1}: {str(e)}")
                        continue

            if not self.scraped_content:
                self.log_activity("WARNING", "No content scraped from Google, using fallback")
                return self.search_with_duckduckgo(query, max_results)

            summary = self.generate_summary(query)
            
            self.current_status = "complete"
            self.log_activity("COMPLETE", "Google search completed successfully!")
            
            return {
                'query': query,
                'search_results': self.search_results,
                'scraped_content': self.scraped_content,
                'summary': summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.current_status = "error"
            error_msg = f"Error during Google search: {str(e)}"
            self.log_activity("ERROR", error_msg)
            # Fallback to DuckDuckGo
            return self.search_with_duckduckgo(query, max_results)
        """Alternative search using DuckDuckGo (more bot-friendly)"""
        self.current_status = "running"
        self.search_results = []
        self.scraped_content = []
        
        self.log_activity("START", f"Starting DuckDuckGo search for: {query}")
        
        try:
            with sync_playwright() as p:
                self.log_activity("BROWSER", "Launching Chrome browser...")
                
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ]
                )

                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                
                page = context.new_page()

                self.log_activity("BROWSER", "Navigating to DuckDuckGo...")
                page.goto("https://duckduckgo.com/", wait_until="domcontentloaded", timeout=30000)

                self.log_activity("BROWSER", f"Searching for: {query}")
                
                # DuckDuckGo search input
                search_input = page.locator("input[name='q']").first
                search_input.fill(query)
                search_input.press("Enter")
                
                # Wait for results
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # Take screenshot
                screenshot_bytes = self.get_screenshot(page)
                if screenshot_bytes:
                    self.log_activity("SCREENSHOT", "Captured DuckDuckGo results page")

                self.log_activity("SCRAPING", "Extracting DuckDuckGo search results...")
                self.search_results = self.extract_duckduckgo_results(page)

                if not self.search_results:
                    self.log_activity("WARNING", "No DuckDuckGo results found, trying fallback method...")
                    # Fallback to direct API search
                    self.search_results = self.fallback_search_api(query)

                self.log_activity("INFO", f"Starting to scrape {min(max_results, len(self.search_results))} results...")
                
                for i, result in enumerate(self.search_results[:max_results]):
                    try:
                        self.log_activity("PROGRESS", f"Scraping result {i+1}/{min(max_results, len(self.search_results))}: {result['title'][:50]}...")
                        content = self.scrape_webpage_content(result['url'])
                        self.scraped_content.append({
                            'title': result['title'],
                            'url': result['url'],
                            'snippet': result['snippet'],
                            'content': content
                        })
                    except Exception as e:
                        self.log_activity("WARNING", f"Failed to scrape result {i+1}: {str(e)}")
                        continue

                browser.close()

            # If no content scraped, use fallback
            if not self.scraped_content:
                self.log_activity("INFO", "No content scraped, using fallback search method...")
                return self.fallback_search_and_summarize(query, max_results)

            summary = self.generate_summary(query)
            
            self.current_status = "complete"
            self.log_activity("COMPLETE", "Search and summarization completed successfully!")
            
            return {
                'query': query,
                'search_results': self.search_results,
                'scraped_content': self.scraped_content,
                'summary': summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.current_status = "error"
            error_msg = f"Error during DuckDuckGo search: {str(e)}"
            self.log_activity("ERROR", error_msg)
            # Try fallback method
            return self.fallback_search_and_summarize(query, max_results)

    def extract_duckduckgo_results(self, page):
        """Extract search results from DuckDuckGo"""
        try:
            html_content = page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            results = []
            # DuckDuckGo result selectors
            search_containers = soup.select('article[data-testid="result"], .nrn-react-div article, .result')
            
            self.log_activity("INFO", f"Found {len(search_containers)} DuckDuckGo result containers")
            
            for container in search_containers[:10]:
                try:
                    # Title
                    title_element = container.select_one('h2 a, .result__title a, [data-testid="result-title-a"]')
                    title = title_element.get_text().strip() if title_element else "No title"
                    
                    # URL
                    url = title_element.get('href', '') if title_element else ""
                    
                    # Snippet
                    snippet_element = container.select_one('[data-testid="result-snippet"], .result__snippet, .result__body')
                    snippet = snippet_element.get_text().strip() if snippet_element else "No description"
                    
                    if title != "No title" and url and url.startswith('http'):
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet
                        })
                        
                except Exception as e:
                    continue
            
            self.log_activity("SUCCESS", f"Extracted {len(results)} DuckDuckGo search results")
            return results
            
        except Exception as e:
            self.log_activity("ERROR", f"Error extracting DuckDuckGo results: {str(e)}")
            return []

    def fallback_search_api(self, query):
        """Fallback search using a simple web search approach"""
        try:
            self.log_activity("FALLBACK", "Using fallback search method...")
            
            # Create some basic search results based on common sources
            fallback_results = []
            
            # You can add more sophisticated fallback logic here
            # For now, we'll create some example results
            search_terms = query.lower().split()
            
            if any(term in ['ai', 'artificial', 'intelligence'] for term in search_terms):
                fallback_results.extend([
                    {
                        'title': 'Artificial Intelligence Trends - MIT Technology Review',
                        'url': 'https://www.technologyreview.com/topic/artificial-intelligence/',
                        'snippet': 'Latest developments in artificial intelligence research and applications.'
                    },
                    {
                        'title': 'AI News and Research - OpenAI',
                        'url': 'https://openai.com/blog',
                        'snippet': 'Research updates and insights from OpenAI on artificial intelligence.'
                    }
                ])
            
            if any(term in ['2024', 'trends', 'latest'] for term in search_terms):
                fallback_results.extend([
                    {
                        'title': 'Tech Trends 2024 - Forbes',
                        'url': 'https://www.forbes.com/technology/',
                        'snippet': 'Latest technology trends and innovations for 2024.'
                    }
                ])
            
            return fallback_results[:5]
            
        except Exception as e:
            self.log_activity("ERROR", f"Fallback search failed: {str(e)}")
            return []

    def fallback_search_and_summarize(self, query, max_results=5):
        """Complete fallback search and summarize method"""
        try:
            self.log_activity("FALLBACK", "Using complete fallback method...")
            
            # Get fallback results
            self.search_results = self.fallback_search_api(query)
            
            if not self.search_results:
                # Create a basic AI-generated response without web scraping
                return self.generate_ai_only_response(query)
            
            # Scrape the fallback results
            for i, result in enumerate(self.search_results[:max_results]):
                try:
                    self.log_activity("PROGRESS", f"Scraping fallback result {i+1}: {result['title'][:50]}...")
                    content = self.scrape_webpage_content(result['url'])
                    self.scraped_content.append({
                        'title': result['title'],
                        'url': result['url'],
                        'snippet': result['snippet'],
                        'content': content
                    })
                except Exception as e:
                    self.log_activity("WARNING", f"Failed to scrape fallback result {i+1}: {str(e)}")
                    continue
            
            if self.scraped_content:
                summary = self.generate_summary(query)
            else:
                summary = self.generate_ai_only_response(query)['summary']
            
            self.current_status = "complete"
            self.log_activity("COMPLETE", "Fallback search completed!")
            
            return {
                'query': query,
                'search_results': self.search_results,
                'scraped_content': self.scraped_content,
                'summary': summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return self.generate_ai_only_response(query)

    def generate_ai_only_response(self, query):
        """Generate response using only AI knowledge when web scraping fails"""
        try:
            self.log_activity("AI", "Generating AI-only response (no web scraping)...")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant. The user asked a question but web search is currently unavailable. Provide a comprehensive answer based on your training data. Be clear that this information is based on your knowledge cutoff and may not include the very latest developments."
                    },
                    {
                        "role": "user",
                        "content": f"Please provide a comprehensive answer about: {query}"
                    }
                ],
                max_tokens=1000,
                temperature=0.3
            )
            
            summary = response.choices[0].message.content
            
            # Add disclaimer
            summary = f"**Note: Web search is currently unavailable, so this response is based on AI knowledge only and may not include the very latest information.**\n\n{summary}"
            
            self.current_status = "complete"
            self.log_activity("COMPLETE", "AI-only response generated successfully!")
            
            return {
                'query': query,
                'search_results': [],
                'scraped_content': [],
                'summary': summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.current_status = "error"
            error_msg = f"Even AI-only response failed: {str(e)}"
            self.log_activity("ERROR", error_msg)
            return {
                'error': error_msg,
                'query': query,
                'timestamp': datetime.now().isoformat()
            }

    def search_and_summarize(self, query, max_results=5):
        """Main search method with multiple fallback strategies"""
        try:
            # Try DuckDuckGo first (more bot-friendly than Google)
            return self.search_with_duckduckgo(query, max_results)
        except Exception as e:
            self.log_activity("ERROR", f"DuckDuckGo search failed: {str(e)}")
            # Fallback to AI-only response
            return self.generate_ai_only_response(query)

# Initialize session state
if 'bot' not in st.session_state:
    st.session_state.bot = StreamlitBrowserSearchBot()
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'openai_configured' not in st.session_state:
    st.session_state.openai_configured = False
if 'activity_logs' not in st.session_state:
    st.session_state.activity_logs = []

def main():
    st.markdown("""
    <div class="main-header">
        <h1>🤖 Autonomous Browser Search Bot</h1>
        <p>AI-powered web search with real-time browser automation</p>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.header("⚙️ Configuration")
        
        st.subheader("🔑 OpenAI API Key")
        api_key = st.text_input(
            "Enter your OpenAI API Key:",
            type="password",
            help="Your OpenAI API key is required for AI-powered summarization"
        )
        
        if api_key and not st.session_state.openai_configured:
            with st.spinner("Configuring OpenAI..."):
                success, message = st.session_state.bot.initialize_openai(api_key)
                if success:
                    st.session_state.openai_configured = True
                    st.success(message)
                else:
                    st.error(message)
        
        if st.session_state.openai_configured:
            st.success("✅ OpenAI configured successfully!")
        
        st.divider()
        
        st.subheader("🔍 Search Settings")
        max_results = st.slider("Max results to scrape:", 1, 10, 5)
        
        st.subheader("🔧 Search Engine")
        search_engine = st.radio(
            "Choose search engine:",
            ["DuckDuckGo (Recommended)", "Google (May be blocked)", "AI-Only (No web search)"],
            help="DuckDuckGo is more bot-friendly and less likely to be blocked"
        )
        
        st.divider()
        
        st.subheader("🧪 Test Queries")
        test_queries = [
            "artificial intelligence trends 2024",
            "climate change solutions",
            "latest smartphone reviews",
            "healthy recipes for dinner",
            "stock market analysis today"
        ]
        
        selected_test = st.selectbox("Select a test query:", [""] + test_queries)
        if st.button("Use Test Query") and selected_test:
            st.session_state.search_query = selected_test
            st.rerun()

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("🔍 Search Interface")
        
        search_query = st.text_input(
            "Enter your search query:",
            value=st.session_state.get('search_query', ''),
            placeholder="e.g., 'latest AI developments in healthcare'"
        )
        
        col_search, col_clear = st.columns([3, 1])
        
        with col_search:
            search_button = st.button(
                "🚀 Start Search",
                disabled=not st.session_state.openai_configured or not search_query.strip(),
                type="primary"
            )
        
        with col_clear:
            if st.button("🗑️ Clear Results"):
                st.session_state.search_results = None
                st.session_state.bot = StreamlitBrowserSearchBot()
                st.session_state.activity_logs = []
                st.rerun()

        # Status indicator
        if st.session_state.bot.current_status == "running":
            st.markdown('<span class="status-indicator status-running">🔄 RUNNING</span>', unsafe_allow_html=True)
        elif st.session_state.bot.current_status == "complete":
            st.markdown('<span class="status-indicator status-complete">✅ COMPLETE</span>', unsafe_allow_html=True)
        elif st.session_state.bot.current_status == "error":
            st.markdown('<span class="status-indicator status-error">❌ ERROR</span>', unsafe_allow_html=True)

    with col2:
        st.header("📸 Live Browser View")
        screenshot_placeholder = st.empty()
        
        # Display screenshot if available
        try:
            if not st.session_state.bot.screenshot_queue.empty():
                latest_screenshot = None
                # Get the latest screenshot
                while not st.session_state.bot.screenshot_queue.empty():
                    latest_screenshot = st.session_state.bot.screenshot_queue.get()
                
                if latest_screenshot:
                    image_data = base64.b64decode(latest_screenshot)
                    image = Image.open(BytesIO(image_data))
                    screenshot_placeholder.image(image, caption="Live Browser View", use_column_width=True)
            else:
                screenshot_placeholder.info("No browser activity yet")
        except Exception as e:
            screenshot_placeholder.error(f"Error displaying screenshot: {str(e)}")

    # Handle search request
    if search_button and search_query.strip():
        if not st.session_state.openai_configured:
            st.error("Please configure your OpenAI API key first!")
        else:
            # Reset previous results
            st.session_state.search_results = None
            st.session_state.activity_logs = []
            
            with st.spinner("🤖 AI is searching and analyzing..."):
                if search_engine == "AI-Only (No web search)":
                    results = st.session_state.bot.generate_ai_only_response(search_query.strip())
                elif search_engine == "Google (May be blocked)":
                    results = st.session_state.bot.search_with_google(search_query.strip(), max_results)
                else:  # DuckDuckGo
                    results = st.session_state.bot.search_and_summarize(search_query.strip(), max_results)
                st.session_state.search_results = results
            st.rerun()

    # Activity Log Section
    st.header("📋 Real-time Activity Log")
    
    # Collect activity logs
    new_activity_logs = []
    try:
        while not st.session_state.bot.activity_queue.empty():
            new_activity_logs.append(st.session_state.bot.activity_queue.get_nowait())
    except queue.Empty:
        pass
    
    # Add new logs to session state
    st.session_state.activity_logs.extend(new_activity_logs)
    
    # Display activity logs
    if st.session_state.activity_logs:
        activity_text = ""
        # Show last 25 logs
        for log in st.session_state.activity_logs[-25:]:
            activity_text += f"[{log.timestamp}] {log.action_type}: {log.description}\n"
            if log.details:
                activity_text += f"    └─ {log.details}\n"
        
        st.code(activity_text, language="log")
    else:
        st.info("No activity logged yet. Start a search to see real-time updates!")

    # Results Display Section
    if st.session_state.search_results:
        results = st.session_state.search_results
        
        if 'error' in results:
            st.error(f"❌ Search failed: {results['error']}")
        else:
            st.header("📊 Search Results")
            
            # AI Summary
            st.subheader("🤖 AI-Generated Summary")
            if 'summary' in results and results['summary']:
                st.markdown(results['summary'])
            else:
                st.warning("No summary available")
            
            # Search Results
            search_results_count = len(results.get('search_results', []))
            scraped_content_count = len(results.get('scraped_content', []))
            
            st.subheader(f"🔗 Search Results ({search_results_count} found, {scraped_content_count} scraped)")
            
            if results.get('scraped_content'):
                for i, result in enumerate(results['scraped_content'], 1):
                    with st.expander(f"{i}. {result['title']}", expanded=False):
                        st.write(f"**URL:** {result['url']}")
                        st.write(f"**Snippet:** {result['snippet']}")
                        st.write("**Content Preview:**")
                        content_preview = result['content']
                        if len(content_preview) > 1000:
                            content_preview = content_preview[:1000] + "..."
                        st.text(content_preview)
            else:
                st.warning("No content was successfully scraped.")
            
            # Export Results
            st.subheader("💾 Export Results")
            col_export1, col_export2 = st.columns(2)
            
            with col_export1:
                json_data = json.dumps(results, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📁 Download Results as JSON",
                    data=json_data,
                    file_name=f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
            
            with col_export2:
                # Create a simple text report
                report = f"Search Results Report\n"
                report += f"Query: {results['query']}\n"
                report += f"Timestamp: {results['timestamp']}\n"
                report += f"Results Found: {len(results.get('search_results', []))}\n\n"
                report += f"Summary:\n{results.get('summary', 'No summary available')}\n\n"
                
                for i, result in enumerate(results.get('scraped_content', []), 1):
                    report += f"{i}. {result['title']}\n"
                    report += f"URL: {result['url']}\n"
                    report += f"Content: {result['content'][:500]}...\n\n"
                
                st.download_button(
                    label="📄 Download as Text Report",
                    data=report,
                    file_name=f"search_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain"
                )

if __name__ == "__main__":
    main()