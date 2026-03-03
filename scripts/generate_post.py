#!/usr/bin/env python3
"""
Blogger Auto-Poster – Llama 3 + Unsplash Images
- Model priority: llama3:8b → mistral:7b → falcon:7b → phi
- Reliable images from Unsplash (free, no key)
- Beautiful fallback banners
"""

import os
import sys
import requests
import feedparser
import random
import subprocess
import traceback
import urllib.parse
from datetime import datetime
from pathlib import Path

# Google API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

# ==================== READ SECRETS ====================
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# ==================== CONFIG ====================
MODEL_PRIORITY = ["llama3:8b", "mistral:7b", "falcon:7b", "phi"]
NUM_POSTS_PER_DAY = 1  # one per run (3 runs daily)

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

# ==================== IMAGE – UNSPLASH (ALWAYS WORKS) ====================
def get_unsplash_image(topic_title):
    """Unsplash random image based on topic keywords."""
    try:
        # Extract top 3 keywords
        keywords = '+'.join(topic_title.split()[:3])
        # Unsplash source returns a direct image URL
        response = requests.get(
            f"https://source.unsplash.com/featured/1200x600/?{keywords}",
            timeout=10,
            allow_redirects=False
        )
        if response.status_code == 302 and 'location' in response.headers:
            return response.headers['location']
    except:
        pass
    return None

def create_image_html(title):
    """Generate image HTML with fallback."""
    # Try Unsplash
    img_url = get_unsplash_image(title)
    if img_url:
        return f'''
        <div style="margin-bottom:30px; text-align:center;">
            <img src="{img_url}" alt="{title}"
                 style="width:100%; max-width:900px; height:auto; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.15);">
            <p style="color:#777; font-size:0.8em;">📸 Photo from Unsplash (related to "{title}")</p>
        </div>
        '''
    # Ultimate fallback – beautiful gradient banner
    colors = [
        'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
        'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
        'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
        'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'
    ]
    gradient = random.choice(colors)
    return f'''
    <div style="margin-bottom:30px; text-align:center; background:{gradient}; padding:50px; border-radius:12px; color:white;">
        <span style="font-size:48px;">📰</span>
        <h2 style="color:white;">{title}</h2>
        <p>Today's featured story</p>
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
        print("🔑 Need new refresh token.")
        return None
    except Exception as e:
        log_error("Authentication", str(e))
        return None

def post_to_blogger(title, content, labels=None):
    if labels is None:
        labels = ['AI Generated', 'Trending']
    service = get_blogger_service()
    if not service:
        return False, "Auth failed"

    image_html = create_image_html(title)
    full_content = image_html + content.replace('\n', '<br>')

    post_body = {
        "kind": "blogger#post",
        "title": title,
        "content": f"""
        <div style="font-family:'Segoe UI',Roboto,sans-serif; line-height:1.8; max-width:900px; margin:0 auto;">
            {full_content}
            <hr style="margin:40px 0 20px;">
            <p style="color:#777; font-style:italic; text-align:center;">
                Published automatically on {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}
            </p>
        </div>
        """,
        "labels": labels
    }

    try:
        response = service.posts().insert(blogId=BLOGGER_BLOG_ID, body=post_body).execute()
        print(f"✅ Post published: {response.get('url')}")
        return True, response.get('url')
    except HttpError as e:
        status = e.resp.status
        log_error("Blogger API", str(e), f"HTTP {status}")
        return False, str(e)
    except Exception as e:
        log_error("Blogger API", str(e))
        return False, str(e)

# ==================== FETCH TRENDING TOPICS ====================
def get_trending_topics():
    topics = []
    sources = [
        ('https://news.ycombinator.com/rss', 'Hacker News', 5),
        ('http://feeds.bbci.co.uk/news/rss.xml', 'BBC', 3),
        ('https://techcrunch.com/feed/', 'TechCrunch', 3),
        ('https://www.wired.com/feed/rss', 'Wired', 3),
    ]
    for url, name, lim in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:lim]:
                if entry.title and '[Removed]' not in entry.title:
                    topics.append({
                        'title': entry.title,
                        'description': entry.get('summary', '')[:300],
                        'source': name
                    })
        except Exception as e:
            log_error(f"RSS {name}", str(e))

    if not topics:
        topics = [
            {'title': 'The Rise of Generative AI in Everyday Life', 'description': 'How AI tools are changing work and creativity', 'source': 'Tech'},
            {'title': 'Breakthroughs in Renewable Energy Storage', 'description': 'New battery technologies that could transform the grid', 'source': 'Science'},
            {'title': 'The Future of Space Tourism', 'description': 'Companies like SpaceX and Blue Origin are making space travel accessible', 'source': 'Space'},
        ]
    random.shuffle(topics)
    return topics

# ==================== GENERATE WITH OLLAMA (MODEL PRIORITY) ====================
def generate_with_ollama(prompt, model_list=None):
    if model_list is None:
        model_list = MODEL_PRIORITY

    for model in model_list:
        print(f"\n🤖 Trying model: {model}...")
        try:
            resp = requests.post('http://localhost:11434/api/generate',
                                  json={
                                      "model": model,
                                      "prompt": prompt,
                                      "stream": False,
                                      "options": {
                                          "temperature": 0.8,
                                          "num_predict": 1500,
                                          "top_k": 40,
                                          "top_p": 0.9
                                      }
                                  },
                                  timeout=600)
            if resp.status_code == 200:
                content = resp.json().get('response', '').strip()
                if content and len(content) > 200:
                    print(f"✅ Success with {model} ({len(content)} chars)")
                    return content
        except Exception as e:
            print(f"⚠️ {model} failed: {e}")

    # Ultimate fallback
    print("❌ All models failed. Using emergency fallback.")
    return f"""
    <h2>Today's Topic: {prompt[:100]}...</h2>
    <p>We're discussing an important subject that's generating interest worldwide.</p>
    <h3>Key Points</h3>
    <p>Staying informed helps us understand the world. We'll continue to monitor developments.</p>
    <h3>Conclusion</h3>
    <p>Thank you for reading. More updates coming soon.</p>
    """

def generate_blog_post(topic):
    prompt = f"""You are an expert blog writer. Write a compelling, well-researched blog post based on the following topic.

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

STRUCTURE:
1. **Headline** – use the title as given.
2. **Introduction** – hook the reader with a question, surprising fact, or anecdote.
3. **Main Body** – 3-4 paragraphs with subheadings. Include:
   - Specific examples or case studies
   - Quotes from experts (you can invent plausible ones)
   - Relevant data or statistics
4. **Conclusion** – summarize key takeaways and end with a thought-provoking question or call to action.

TONE: Professional but accessible, engaging, slightly conversational.
LENGTH: 500-700 words.

Write the post in plain text (no markdown). Use proper paragraphs.

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
    print(f"💾 Local backup: {filename}")
    return filename

# ==================== MAIN ====================
def main():
    print("="*60)
    print("🚀 AI BLOGGER – Llama 3 + Unsplash Images")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    missing = []
    if not BLOGGER_BLOG_ID: missing.append("BLOGGER_BLOG_ID")
    if not GOOGLE_CLIENT_ID: missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET: missing.append("GOOGLE_CLIENT_SECRET")
    if not GOOGLE_REFRESH_TOKEN: missing.append("GOOGLE_REFRESH_TOKEN")
    if missing:
        print(f"❌ Missing: {', '.join(missing)}")
        sys.exit(1)
    print("✅ Credentials OK.")

    topics = get_trending_topics()
    if not topics:
        print("❌ No topics.")
        sys.exit(1)

    topic = random.choice(topics)
    print(f"\n🎯 Topic: {topic['title']} ({topic['source']})")

    print("\n✍️ Generating high-quality post with Llama 3...")
    content = generate_blog_post(topic)

    local = save_local_post(topic['title'], content)

    print("\n📤 Posting to Blogger with Unsplash image...")
    success, result = post_to_blogger(
        topic['title'],
        content,
        labels=['AI Generated', topic['source'].replace(' ', '-'), 'Llama3']
    )

    print("\n" + "="*60)
    if success:
        print("✨ SUCCESS! Post published.")
        print(f"📌 {result}")
    else:
        print("⚠️ Blogger failed, but backup saved.")
        print(f"📁 {local}")
        print(f"🔍 Error: {result}")
    print("="*60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted.")
        sys.exit(0)
    except Exception as e:
        log_error("Main", str(e))
        sys.exit(1)
