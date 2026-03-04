#!/usr/bin/env python3
"""
Blogger Auto-Poster – Long Form + News Images + Logo
- Fetches image from RSS feed (if available)
- Falls back to Unsplash
- Generates 3000-4000 word posts with synopsis and sections
- Adds logo at bottom (base64 embedded)
"""

import os
import sys
import requests
import feedparser
import random
import subprocess
import traceback
import urllib.parse
import time
import base64
from datetime import datetime
from pathlib import Path
import json
import re

# Google API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

# For potential image processing (not strictly needed)
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except:
    PILLOW_AVAILABLE = False

# ==================== READ SECRETS ====================
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# ==================== CONFIG ====================
PRIMARY_MODEL = "llama3:8b"
FALLBACK_MODEL = "phi"
LOGO_PATH = Path("logo.png")  # Your logo file (place in repo root)

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
def extract_image_from_entry(entry):
    """Try to extract image URL from RSS entry (media:content, enclosure, etc.)"""
    # Check media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
    # Check media:thumbnail
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        for thumb in entry.media_thumbnail:
            if 'url' in thumb:
                return thumb['url']
    # Check enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return enc.get('href') or enc.get('url')
    # Some feeds use media:group
    if hasattr(entry, 'media_group') and entry.media_group:
        for group in entry.media_group:
            if hasattr(group, 'media_content'):
                for mc in group.media_content:
                    if 'url' in mc:
                        return mc['url']
    return None

def get_unsplash_image(keywords):
    """Fallback to Unsplash if no image in feed"""
    try:
        if not keywords:
            keywords = "news"
        clean = '+'.join(keywords.split()[:3])
        resp = requests.get(
            f"https://source.unsplash.com/featured/1200x600/?{clean}",
            timeout=10,
            allow_redirects=False
        )
        if resp.status_code == 302 and 'location' in resp.headers:
            return resp.headers['location']
    except:
        pass
    return None

def get_image_url(entry, topic_title):
    """Main function: try RSS first, then Unsplash"""
    url = extract_image_from_entry(entry)
    if url:
        print(f"🖼️ Found image in RSS feed: {url[:60]}...")
        return url
    print("🖼️ No image in RSS, trying Unsplash...")
    return get_unsplash_image(topic_title)

def create_image_html(img_url, title):
    """Generate HTML for the image"""
    if not img_url:
        return ''  # No image
    return f'''
    <div style="margin-bottom:30px; text-align:center;">
        <img src="{img_url}" alt="{title}"
             style="width:100%; max-width:900px; height:auto; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.15);">
        <p style="color:#777; font-size:0.8em;">📸 Image source: {'Unsplash' if 'unsplash' in img_url else 'News feed'}</p>
    </div>
    '''

# ==================== LOGO (BASE64) ====================
def get_logo_base64():
    """Read logo.png and return base64 string"""
    if not LOGO_PATH.exists():
        print("⚠️ Logo file not found, skipping logo.")
        return None
    try:
        with open(LOGO_PATH, 'rb') as f:
            img_data = f.read()
        return base64.b64encode(img_data).decode('utf-8')
    except Exception as e:
        log_error("Logo read", str(e))
        return None

def create_logo_html():
    """Generate HTML for logo at bottom"""
    b64 = get_logo_base64()
    if not b64:
        return ''
    return f'''
    <div style="margin-top:40px; text-align:center; padding:20px; border-top:1px solid #eaeaea;">
        <img src="data:image/png;base64,{b64}" alt="Blog Logo" style="max-width:200px; height:auto;">
        <p style="color:#777; font-size:0.8em;">© {datetime.now().year} ReadContext</p>
    </div>
    '''

# ==================== BLOGGER AUTH ====================
def get_blogger_service():
    if not all([GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN]):
        print("❌ Missing Google credentials.")
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
        print("🔄 Refreshing access token...")
        creds.refresh(Request())
        print("✅ Token refreshed.")
        service = build('blogger', 'v3', credentials=creds)
        blog_info = service.blogs().get(blogId=BLOGGER_BLOG_ID).execute()
        print(f"✅ Blog verified: {blog_info.get('name')}")
        return service
    except RefreshError as e:
        log_error("Token Refresh", str(e))
        print("🔑 Need new refresh token from OAuth Playground.")
        return None
    except Exception as e:
        log_error("Authentication", str(e))
        return None

def post_to_blogger(title, content, img_url, labels=None):
    if labels is None:
        labels = ['AI Generated', 'Trending', 'LongForm']

    service = get_blogger_service()
    if not service:
        return False, "Auth failed"

    # Build post content: image at top, then article, then logo
    image_html = create_image_html(img_url, title)
    logo_html = create_logo_html()
    full_content = image_html + content.replace('\n', '<br>') + logo_html

    post_body = {
        "kind": "blogger#post",
        "title": title,
        "content": f"""
        <div style="font-family:'Segoe UI', Roboto, sans-serif; line-height:1.8; max-width:900px; margin:0 auto;">
            {full_content}
            <hr style="margin:40px 0 20px;">
            <p style="color:#777; font-style:italic; text-align:center;">
                Published on {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}
            </p>
        </div>
        """,
        "labels": labels
    }

    try:
        response = service.posts().insert(blogId=BLOGGER_BLOG_ID, body=post_body).execute()
        print(f"✅ Post published: {response.get('url')}")
        return True, response.get('url')
    except Exception as e:
        log_error("Blogger API", str(e))
        return False, str(e)

# ==================== FETCH TRENDING TOPICS (with full entry) ====================
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
                        'entry': entry  # Store full entry for image extraction
                    })
        except Exception as e:
            log_error(f"RSS {name}", str(e))

    if not topics:
        topics = [
            {'title': 'The Future of AI', 'description': 'How AI is transforming our world', 'source': 'Tech', 'entry': None},
            {'title': 'Climate Tech Innovations', 'description': 'Breakthroughs in green energy', 'source': 'Science', 'entry': None},
        ]
    random.shuffle(topics)
    return topics

# ==================== GENERATE LONG CONTENT ====================
def generate_with_ollama(prompt, model=PRIMARY_MODEL):
    """Generate text using Ollama – increased token limit for long posts"""
    # Try API
    try:
        resp = requests.post('http://localhost:11434/api/generate',
                              json={
                                  "model": model,
                                  "prompt": prompt,
                                  "stream": False,
                                  "options": {
                                      "temperature": 0.8,
                                      "num_predict": 4096,   # ~4000 words
                                      "top_k": 40,
                                      "top_p": 0.9
                                  }
                              },
                              timeout=600)  # 10 minutes
        if resp.status_code == 200:
            content = resp.json().get('response', '').strip()
            if content:
                return content
    except Exception as e:
        print(f"⚠️ {model} API error: {e}")

    # Fallback to CLI
    try:
        result = subprocess.run(
            ['/usr/local/bin/ollama', 'run', model, prompt],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ {model} CLI error: {e}")

    # If primary fails, try fallback
    if model != FALLBACK_MODEL:
        print(f"🔄 Falling back to {FALLBACK_MODEL}...")
        return generate_with_ollama(prompt, FALLBACK_MODEL)

    return None

def generate_blog_post(topic):
    """Craft a detailed prompt for a long, structured post."""
    prompt = f"""Write a comprehensive, in-depth blog post about the following topic.

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

REQUIREMENTS:
- Length: 3000-4000 words
- Structure:
  1. **Synopsis/Executive Summary** – a brief overview of the entire post (2-3 paragraphs)
  2. **Introduction** – hook the reader, explain why this topic matters
  3. **Background** – provide context, history, or key facts
  4. **Main Analysis** – break into 4-6 subsections with subheadings (e.g., "The Current Situation", "Key Players", "Challenges", "Future Outlook")
  5. **Implications** – what does this mean for readers, industry, or society?
  6. **Conclusion** – summarize main points and end with a thought-provoking question or call to action
- Include specific examples, data points, or expert quotes (you can invent plausible ones)
- Write in a professional but accessible tone
- Use proper paragraphs and subheadings (marked as <h2>, <h3>)

Write the post in plain text with HTML tags for headings.

POST:
"""
    return generate_with_ollama(prompt)

# ==================== LOCAL BACKUP ====================
def save_local_post(title, content):
    slug = title.lower().replace(' ', '-')[:50]
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = POSTS_DIR / f"{timestamp}_{slug}.md"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# {title}\n\n{content}")
    print(f"💾 Local backup saved: {filename}")
    return filename

# ==================== MAIN ====================
def main():
    print("="*70)
    print("🚀 AI BLOGGER – Long Form + News Images + Logo")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Check secrets
    missing = []
    if not BLOGGER_BLOG_ID: missing.append("BLOGGER_BLOG_ID")
    if not GOOGLE_CLIENT_ID: missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET: missing.append("GOOGLE_CLIENT_SECRET")
    if not GOOGLE_REFRESH_TOKEN: missing.append("GOOGLE_REFRESH_TOKEN")
    if missing:
        print(f"❌ Missing secrets: {', '.join(missing)}")
        sys.exit(1)
    print("✅ All credentials present")

    # Get topics
    topics = get_trending_topics()
    if not topics:
        print("❌ No topics available")
        sys.exit(1)

    topic = random.choice(topics)
    print(f"\n🎯 Topic: {topic['title']}")
    print(f"📌 Source: {topic['source']}")

    # Get image from RSS entry (if available)
    img_url = None
    if topic.get('entry'):
        img_url = get_image_url(topic['entry'], topic['title'])
    if not img_url:
        img_url = get_unsplash_image(topic['title'])
    if img_url:
        print(f"✅ Image URL: {img_url[:60]}...")
    else:
        print("⚠️ No image found, proceeding without image.")

    # Generate long content
    print("\n✍️ Generating long-form content (3000-4000 words)...")
    content = generate_blog_post(topic)
    if not content:
        print("❌ Content generation failed")
        sys.exit(1)
    print(f"✅ Content generated ({len(content)} chars)")

    # Save backup
    local_file = save_local_post(topic['title'], content)

    # Post to Blogger
    print("\n📤 Posting to Blogger...")
    success, result = post_to_blogger(
        topic['title'],
        content,
        img_url,
        labels=['AI Generated', topic['source'].replace(' ', '-'), 'LongForm']
    )

    print("\n" + "="*70)
    if success:
        print("✨ SUCCESS! Post published!")
        print(f"📌 URL: {result}")
        print(f"📁 Backup: {local_file}")
    else:
        print(f"⚠️ Blogger posting failed: {result}")
        print(f"✅ Backup saved at: {local_file}")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
        sys.exit(0)
    except Exception as e:
        log_error("Main execution", str(e))
        sys.exit(1)
