#!/usr/bin/env python3
"""
Blogger Auto-Poster – AirLLM Edition (13B/7B on CPU) – FINAL FIXED VERSION
- Auto-detects working sitemap URL for Google ping
- Improved Search Console error handling
- Falls back to Ollama (llama3:8b / phi) if AirLLM fails
- All existing SEO & image features preserved
"""

import os
import sys
import requests
import feedparser
import random
import subprocess
import traceback
import urllib.parse
import base64
import json
import time
from datetime import datetime
from pathlib import Path

# Google APIs
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

# AirLLM – optional
try:
    from airllm import AutoModel
    AIRLLM_AVAILABLE = True
except ImportError:
    AIRLLM_AVAILABLE = False

# ==================== CONFIG ====================
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")
GSC_SERVICE_ACCOUNT_JSON = os.getenv("GSC_SERVICE_ACCOUNT_JSON")

# Model selection – 7B is safer on GitHub runners
AIRLLM_MODEL = "v2ray/Llama-2-7B"          # 7B – works on CPU with ~6GB RAM
# AIRLLM_MODEL = "v2ray/Llama-2-13B"        # 13B – may exceed memory, use cautiously
OLLAMA_PRIMARY = "llama3:8b"
OLLAMA_FALLBACK = "phi"

LOGO_PATH = Path("logo.png")
BLOG_URL = "https://readcontext.blogspot.com"

# We'll auto-detect the correct sitemap URL
SITEMAP_CANDIDATES = [
    f"{BLOG_URL}/sitemap.xml",
    f"{BLOG_URL}/atom.xml?redirect=false&start-index=1&max-results=500",
    f"{BLOG_URL}/feeds/posts/default",
]
SITEMAP_URL = None  # will be set by test_sitemap()

# ==================== SETUP ====================
CACHE_DIR = Path(".blog-cache")
POSTS_DIR = Path("_posts")
CACHE_DIR.mkdir(exist_ok=True)
POSTS_DIR.mkdir(exist_ok=True)

POSTS_LOG = CACHE_DIR / "posts_log.json"
if POSTS_LOG.exists():
    with open(POSTS_LOG, 'r') as f:
        posts_log = json.load(f)
else:
    posts_log = []

def log_error(step, error, details=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n❌ ERROR at {timestamp}")
    print(f"   Step: {step}")
    print(f"   Error: {error}")
    if details:
        print(f"   Details: {details}")
    print(f"   Traceback: {traceback.format_exc()}")

def test_sitemap():
    """Find a working sitemap URL by trying candidates."""
    global SITEMAP_URL
    for url in SITEMAP_CANDIDATES:
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            if r.status_code == 200:
                SITEMAP_URL = url
                print(f"✅ Using sitemap: {url}")
                return
        except:
            continue
    # Fallback to the first candidate (will be used anyway)
    SITEMAP_URL = SITEMAP_CANDIDATES[0]
    print(f"⚠️ No working sitemap found, using default: {SITEMAP_URL}")

# ==================== IMAGE FETCHING ====================
def extract_rss_image(entry):
    if hasattr(entry, 'media_content') and entry.media_content:
        for m in entry.media_content:
            if 'url' in m:
                return m['url']
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for e in entry.enclosures:
            if e.get('type', '').startswith('image/'):
                return e.get('href') or e.get('url')
    if hasattr(entry, 'links'):
        for link in entry.links:
            if link.get('rel') == 'enclosure' and link.get('type', '').startswith('image/'):
                return link.get('href')
    return None

def get_unsplash_url(keywords):
    try:
        kw = '+'.join(keywords.split()[:3])
        resp = requests.get(
            f"https://source.unsplash.com/featured/1200x600/?{kw}",
            timeout=10,
            allow_redirects=False
        )
        if resp.status_code == 302 and 'location' in resp.headers:
            return resp.headers['location']
    except:
        pass
    return None

def get_picsum_url():
    return f"https://picsum.photos/1200/600?random={random.randint(1,100000)}"

def get_image_url(entry, title):
    url = extract_rss_image(entry) if entry else None
    if url:
        print(f"🖼️ RSS image found")
        return url
    url = get_unsplash_url(title)
    if url:
        print(f"🖼️ Unsplash image found")
        return url
    print(f"🖼️ Using Picsum placeholder")
    return get_picsum_url()

def create_image_html(img_url, title):
    if not img_url:
        return f'''
        <div style="margin-bottom:30px; text-align:center; background:linear-gradient(135deg,#667eea,#764ba2); padding:50px; border-radius:12px; color:white;">
            <span style="font-size:48px;">📰</span>
            <h2 style="color:white;">{title}</h2>
            <p>Today's featured story</p>
        </div>
        '''
    return f'''
    <div style="margin-bottom:30px; text-align:center;">
        <img src="{img_url}" alt="{title}"
             style="width:100%; max-width:900px; height:auto; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.15);">
        <p style="color:#777; font-size:0.8em;">📸 Image source</p>
    </div>
    '''

# ==================== LOGO ====================
def get_logo_base64():
    if not LOGO_PATH.exists():
        return None
    try:
        with open(LOGO_PATH, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except:
        return None

def create_logo_html():
    b64 = get_logo_base64()
    if not b64:
        return ''
    return f'''
    <div style="margin-top:40px; text-align:center; padding:20px; border-top:1px solid #eaeaea;">
        <img src="data:image/png;base64,{b64}" alt="Logo" style="max-width:200px; margin:0 auto; display:block;">
        <p style="color:#777; margin-top:10px;">© {datetime.now().year} ReadContext</p>
    </div>
    '''

# ==================== INTERNAL LINKING ====================
def get_related_posts_html(current_title, max_links=3):
    if not posts_log:
        return ""
    candidates = [p for p in posts_log if p['title'] != current_title]
    if len(candidates) < 1:
        return ""
    selected = random.sample(candidates, min(max_links, len(candidates)))
    html = '<h2>📚 Related Posts</h2><ul style="list-style:none; padding:0;">'
    for p in selected:
        html += f'<li style="margin-bottom:10px;"><a href="{p["url"]}" style="text-decoration:none; color:#F36C21;">{p["title"]}</a></li>'
    html += '</ul>'
    return html

# ==================== PING GOOGLE ====================
def ping_google():
    global SITEMAP_URL
    if not SITEMAP_URL:
        test_sitemap()
    try:
        ping_url = f"https://www.google.com/ping?sitemap={SITEMAP_URL}"
        r = requests.get(ping_url, timeout=10)
        if r.status_code == 200:
            print("✅ Google pinged successfully")
        else:
            print(f"⚠️ Google ping returned {r.status_code} – check sitemap URL: {SITEMAP_URL}")
    except Exception as e:
        log_error("Google Ping", str(e))

# ==================== SEARCH CONSOLE ====================
def submit_to_search_console(post_url):
    if not GSC_SERVICE_ACCOUNT_JSON:
        print("⚠️ GSC_SERVICE_ACCOUNT_JSON not set – skipping Search Console submission.")
        return False
    try:
        # Clean the JSON string (remove any extra quotes)
        json_str = GSC_SERVICE_ACCOUNT_JSON.strip()
        if json_str.startswith('"') and json_str.endswith('"'):
            json_str = json_str[1:-1].replace('\\"', '"')
        service_account_info = json.loads(json_str)
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/indexing"]
        )
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json"
        }
        if not credentials.valid:
            credentials.refresh(Request())
        data = {
            "url": post_url,
            "type": "URL_UPDATED"
        }
        resp = requests.post(
            "https://indexing.googleapis.com/v3/urlNotifications:publish",
            headers=headers,
            json=data,
            timeout=10
        )
        if resp.status_code == 200:
            print("✅ Submitted to Google Search Console via Service Account")
            return True
        else:
            error_body = resp.text
            print(f"⚠️ Search Console API error: {resp.status_code} {error_body}")
            if resp.status_code == 401:
                print("   🔑 Ensure the service account email is added as an owner in Search Console.")
            return False
    except json.JSONDecodeError as e:
        log_error("Search Console JSON parse", str(e))
        print("   🔧 Check that GSC_SERVICE_ACCOUNT_JSON contains the entire JSON key (including braces).")
        return False
    except Exception as e:
        log_error("Search Console API", str(e))
        return False

# ==================== BLOGGER AUTH ====================
def get_blogger_service():
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        print("❌ Missing Google Blogger credentials.")
        return None
    try:
        creds = Credentials(
            token=None,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/blogger"]
        )
        creds.refresh(Request())
        service = build('blogger', 'v3', credentials=creds)
        blog_info = service.blogs().get(blogId=BLOGGER_BLOG_ID).execute()
        print(f"✅ Blog verified: {blog_info.get('name')}")
        return service
    except Exception as e:
        log_error("Blogger Auth", str(e))
        return None

def post_to_blogger(title, content, meta_description, img_url, labels):
    service = get_blogger_service()
    if not service:
        return False, "Auth failed"

    image_html = create_image_html(img_url, title)
    related_html = get_related_posts_html(title)
    logo_html = create_logo_html()
    full_content = image_html + content + related_html + logo_html

    post_body = {
        "kind": "blogger#post",
        "title": title,
        "content": f"""
        <div style="font-family:Georgia,serif; line-height:1.8; max-width:900px; margin:0 auto;">
            {full_content}
            <hr>
            <p style="color:#777; text-align:center;">Published on {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}</p>
        </div>
        """,
        "labels": labels,
        "metaDescription": meta_description[:160] if meta_description else None
    }

    try:
        res = service.posts().insert(blogId=BLOGGER_BLOG_ID, body=post_body).execute()
        post_url = res.get('url')
        print(f"✅ Post published: {post_url}")
        posts_log.append({
            "title": title,
            "url": post_url,
            "date": datetime.now().isoformat()
        })
        with open(POSTS_LOG, 'w') as f:
            json.dump(posts_log[-100:], f, indent=2)
        return True, post_url
    except Exception as e:
        log_error("Blogger API", str(e))
        return False, str(e)

# ==================== TOPICS ====================
def get_trending_topics():
    topics = []
    sources = [
        ('https://news.ycombinator.com/rss', 'Hacker News', 3),
        ('http://feeds.bbci.co.uk/news/rss.xml', 'BBC', 2),
        ('https://techcrunch.com/feed/', 'TechCrunch', 2),
    ]
    for url, name, limit in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                if entry.title and '[Removed]' not in entry.title:
                    topics.append({
                        'title': entry.title,
                        'description': entry.get('summary', '')[:500],
                        'source': name,
                        'entry': entry
                    })
        except:
            pass
    if not topics:
        topics = [{'title': 'The Future of AI', 'description': 'AI transforming lives', 'source': 'Tech', 'entry': None}]
    random.shuffle(topics)
    return topics

# ==================== AIRLLM GENERATION ====================
def generate_with_airllm(prompt, model_name=AIRLLM_MODEL):
    if not AIRLLM_AVAILABLE:
        return None
    try:
        print(f"🤖 Loading AirLLM model {model_name}...")
        model = AutoModel.from_pretrained(model_name, compression='4bit')
        print("✅ Model loaded.")
        input_ids = model.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).input_ids
        if hasattr(model, 'device'):
            input_ids = input_ids.to(model.device)
        print("⏳ Generating (this may take a long time on CPU)...")
        output = model.generate(
            input_ids,
            max_new_tokens=4096,
            use_cache=True,
            temperature=0.8,
            do_sample=True,
            top_p=0.9
        )
        result = model.tokenizer.decode(output[0], skip_special_tokens=True)
        if result.startswith(prompt):
            result = result[len(prompt):].strip()
        print(f"✅ AirLLM generation complete ({len(result)} chars)")
        return result
    except Exception as e:
        log_error("AirLLM Generation", str(e))
        return None

# ==================== OLLAMA GENERATION ====================
def generate_with_ollama(prompt, model):
    try:
        # Try API first
        resp = requests.post('http://localhost:11434/api/generate',
                              json={
                                  "model": model,
                                  "prompt": prompt,
                                  "stream": False,
                                  "options": {"temperature": 0.7, "num_predict": 4096}
                              },
                              timeout=600)
        if resp.status_code == 200:
            content = resp.json().get('response', '').strip()
            if content:
                return content
    except Exception as e:
        print(f"⚠️ {model} API error: {e}")
    # Fallback to CLI
    try:
        result = subprocess.run(['/usr/local/bin/ollama', 'run', model, prompt],
                                capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ {model} CLI error: {e}")
    return None

def generate_blog_post(topic):
    """Enhanced prompt for high‑quality output."""
    prompt = f"""You are a world‑class journalist and blogger. Write an in‑depth, engaging, and perfectly structured blog post on the following topic. Use proper HTML tags for headings.

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

REQUIREMENTS:
- Length: 3500‑4500 words.
- Structure:
  1. <h1>{topic['title']}</h1>
  2. <h2>Synopsis</h2> – a compelling 2‑paragraph summary.
  3. <h2>Introduction</h2> – hook the reader.
  4. <h2>Background / Context</h2>
  5. <h2>Main Analysis</h2> – break into at least 3 sub‑sections with <h3> subheadings. Include data, examples, and expert quotes.
  6. <h2>Implications & Future Outlook</h2>
  7. <h2>Conclusion</h2>
- Use clear, accessible language but maintain authority.
- Avoid any meta‑comments – just output the article.

Write the post now, using HTML tags.
"""
    # Try AirLLM first (if installed)
    if AIRLLM_AVAILABLE:
        content = generate_with_airllm(prompt)
        if content:
            return content, "Generated by AirLLM"
        else:
            print("⚠️ AirLLM failed, falling back to Ollama.")
    else:
        print("ℹ️ AirLLM not installed, using Ollama.")

    # Try Ollama primary model
    content = generate_with_ollama(prompt, OLLAMA_PRIMARY)
    if content:
        return content, f"Generated by {OLLAMA_PRIMARY}"

    # Try Ollama fallback
    print(f"⚠️ {OLLAMA_PRIMARY} failed, falling back to {OLLAMA_FALLBACK}.")
    content = generate_with_ollama(prompt, OLLAMA_FALLBACK)
    if content:
        return content, f"Generated by {OLLAMA_FALLBACK}"

    # Ultimate fallback
    return None, None

def save_local_post(title, content, summary):
    slug = title.lower().replace(' ', '-')[:50]
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
    fname = POSTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
    with open(fname, 'w') as f:
        f.write(f"# {title}\n\n## Summary\n{summary}\n\n{content}")
    return fname

# ==================== MAIN ====================
def main():
    # Find working sitemap URL at start
    test_sitemap()

    print("="*70)
    print("🚀 AI BLOGGER – AirLLM Edition (13B/7B on CPU) – FINAL FIXED")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    missing = [k for k, v in [('BLOGGER_BLOG_ID', BLOGGER_BLOG_ID),
                               ('GOOGLE_CLIENT_ID', GOOGLE_CLIENT_ID),
                               ('GOOGLE_CLIENT_SECRET', GOOGLE_CLIENT_SECRET),
                               ('GOOGLE_REFRESH_TOKEN', GOOGLE_REFRESH_TOKEN)] if not v]
    if missing:
        print(f"❌ Missing Blogger secrets: {', '.join(missing)}")
        sys.exit(1)

    topics = get_trending_topics()
    if not topics:
        print("❌ No topics")
        sys.exit(1)

    topic = random.choice(topics)
    print(f"\n🎯 Topic: {topic['title']} ({topic['source']})")

    img_url = get_image_url(topic.get('entry'), topic['title'])
    if img_url:
        print(f"✅ Image obtained")
    else:
        print("⚠️ No image, using gradient fallback")

    print("\n✍️ Generating high‑quality content (this may take a long time)...")
    content, summary = generate_blog_post(topic)
    if not content:
        print("❌ Generation failed")
        sys.exit(1)
    print(f"✅ Generated {len(content)} chars")
    print(f"📝 Summary: {summary[:100]}...")

    local = save_local_post(topic['title'], content, summary)

    print("\n📤 Posting to Blogger...")
    ok, url = post_to_blogger(
        topic['title'],
        content,
        summary,
        img_url,
        ['AI Generated', topic['source'].replace(' ', '-'), 'AirLLM']
    )

    if ok:
        print("\n🔔 Pinging Google...")
        ping_google()
        if GSC_SERVICE_ACCOUNT_JSON:
            print("\n📤 Submitting to Google Search Console...")
            submit_to_search_console(url)
        print(f"\n✨ SUCCESS! Post published: {url}")
        print(f"📁 Backup: {local}")
    else:
        print(f"\n❌ Failed to publish: {url}\nBackup saved at {local}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error("Main", str(e))
        sys.exit(1)
