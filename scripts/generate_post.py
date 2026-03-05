#!/usr/bin/env python3
"""
Blogger Auto-Poster – Long Form + RSS Images + Logo
- Generates 3000-4000 words per post
- Extracts image from RSS feed (if available)
- Falls back to Unsplash → Picsum → gradient banner
- Adds your logo at the bottom (base64 encoded)
- Designed to run multiple times per day (NUM_POSTS_PER_DAY = 1)
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
from datetime import datetime
from pathlib import Path

# Google API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

# ==================== CONFIG ====================
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

PRIMARY_MODEL = "llama3:8b"
FALLBACK_MODEL = "phi"
LOGO_PATH = Path("logo.png")

# ==================== SETUP ====================
CACHE_DIR = Path(".blog-cache")
POSTS_DIR = Path("_posts")
CACHE_DIR.mkdir(exist_ok=True)
POSTS_DIR.mkdir(exist_ok=True)

def log_error(step, error, details=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n❌ ERROR at {timestamp}")
    print(f"   Step: {step}")
    print(f"   Error: {error}")
    if details:
        print(f"   Details: {details}")
    print(f"   Traceback: {traceback.format_exc()}")

# ==================== IMAGE FETCHING ====================
def extract_rss_image(entry):
    """Extract image URL from RSS entry (media:content, enclosure, etc.)"""
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
    """Try Unsplash (returns redirect URL)"""
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
    """Picsum – always returns a random image (no keywords)"""
    return f"https://picsum.photos/1200/600?random={random.randint(1,100000)}"

def get_image_url(entry, title):
    """Main image function: RSS → Unsplash → Picsum → None"""
    # 1. Try RSS
    url = extract_rss_image(entry) if entry else None
    if url:
        print(f"🖼️ RSS image found")
        return url
    # 2. Try Unsplash
    url = get_unsplash_url(title)
    if url:
        print(f"🖼️ Unsplash image found")
        return url
    # 3. Try Picsum (always works)
    print(f"🖼️ Using Picsum placeholder")
    return get_picsum_url()

def create_image_html(img_url, title):
    if not img_url:
        # Ultimate fallback – gradient banner
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
        <img src="data:image/png;base64,{b64}" alt="Logo" style="max-width:200px;">
        <p style="color:#777;">© {datetime.now().year} ReadContext</p>
    </div>
    '''

# ==================== BLOGGER ====================
def get_blogger_service():
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
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
        return build('blogger', 'v3', credentials=creds)
    except Exception as e:
        log_error("Blogger Auth", str(e))
        return None

def post_to_blogger(title, content, img_url, labels):
    service = get_blogger_service()
    if not service:
        return False, "Auth failed"

    image_html = create_image_html(img_url, title)
    logo_html = create_logo_html()
    full_content = image_html + content + logo_html

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
        "labels": labels
    }

    try:
        res = service.posts().insert(blogId=BLOGGER_BLOG_ID, body=post_body).execute()
        return True, res.get('url')
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

# ==================== GENERATION (CLEAN PROMPT) ====================
def generate_with_ollama(prompt, model=PRIMARY_MODEL):
    # Try API
    try:
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
    except:
        pass
    # Try CLI
    try:
        result = subprocess.run(['/usr/local/bin/ollama', 'run', model, prompt],
                                capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    if model != FALLBACK_MODEL:
        return generate_with_ollama(prompt, FALLBACK_MODEL)
    return None

def generate_blog_post(topic):
    """Prompt that asks only for the post body, no extra text."""
    prompt = f"""Write a detailed, long-form blog post about the following topic. Output only the post content, no additional commentary.

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

Structure:
- Start with an <h1> title (the given title)
- Then an <h2>Synopsis</h2> (2-3 paragraph summary)
- Then <h2>Introduction</h2>
- Then several <h2> sections (at least 4) with detailed analysis, examples, implications
- End with <h2>Conclusion</h2>

Length: 3000-4000 words. Write in clear, engaging prose. Use <h2> for headings, <p> for paragraphs. Do not include any meta comments like "Here's a post..." – just the post itself.
"""
    return generate_with_ollama(prompt)

def save_local_post(title, content):
    slug = title.lower().replace(' ', '-')[:50]
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
    fname = POSTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
    with open(fname, 'w') as f:
        f.write(f"# {title}\n\n{content}")
    return fname

# ==================== MAIN ====================
def main():
    print("="*70)
    print("🚀 AI BLOGGER – Long Form + RSS Images + Logo")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    missing = [k for k, v in [('BLOGGER_BLOG_ID', BLOGGER_BLOG_ID),
                               ('GOOGLE_CLIENT_ID', GOOGLE_CLIENT_ID),
                               ('GOOGLE_CLIENT_SECRET', GOOGLE_CLIENT_SECRET),
                               ('GOOGLE_REFRESH_TOKEN', GOOGLE_REFRESH_TOKEN)] if not v]
    if missing:
        print(f"❌ Missing secrets: {', '.join(missing)}")
        sys.exit(1)

    topics = get_trending_topics()
    if not topics:
        print("❌ No topics")
        sys.exit(1)

    topic = random.choice(topics)
    print(f"\n🎯 Topic: {topic['title']} ({topic['source']})")

    # Get image (RSS → Unsplash → Picsum → None)
    img_url = get_image_url(topic.get('entry'), topic['title'])
    if img_url:
        print(f"✅ Image obtained")
    else:
        print("⚠️ No image, using gradient fallback")

    # Generate content
    print("\n✍️ Generating long content (3000-4000 words)...")
    content = generate_blog_post(topic)
    if not content:
        print("❌ Generation failed")
        sys.exit(1)
    print(f"✅ Generated {len(content)} chars")

    # Local backup
    local = save_local_post(topic['title'], content)

    # Post to Blogger
    print("\n📤 Posting to Blogger...")
    ok, url = post_to_blogger(topic['title'], content, img_url,
                               ['AI Generated', topic['source'].replace(' ', '-'), 'LongForm'])

    print("\n" + "="*70)
    if ok:
        print(f"✨ SUCCESS!\n📌 {url}")
    else:
        print(f"⚠️ Failed: {url}\n✅ Backup: {local}")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error("Main", str(e))
        sys.exit(1)
