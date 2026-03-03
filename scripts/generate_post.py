#!/usr/bin/env python3
import requests
import json
import random
import feedparser
from datetime import datetime, timedelta
import subprocess
import os
import hashlib
import pickle
from pathlib import Path
import html
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# -------------------- BLOGGER CONFIGURATION --------------------
BLOGGER_BLOG_ID = "6965563738161457805"  # Replace with your actual blog ID
# These will come from GitHub Secrets
GOOGLE_CLIENT_SECRET = os.getenv("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")
GOOGLE_REFRESH_TOKEN = os.getenv("1//04uQQOqNFB0CBCgYIARAAGAQSNwF-L9Irra3IuUhVGYzM0FsHR36wHU1RuVl96Wdbe_2hCzg8pAaTipLx3RhRSybN661p0J48IMk")

# -------------------- Cache Setup --------------------
CACHE_DIR = Path(".blog-cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache(key, max_age_hours=24):
    cache_file = CACHE_DIR / f"{key}.pkl"
    if cache_file.exists():
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
            timestamp = data.get('timestamp')
            if timestamp and datetime.now() - timestamp < timedelta(hours=max_age_hours):
                return data.get('value')
    return None

def set_cache(key, value):
    cache_file = CACHE_DIR / f"{key}.pkl"
    with open(cache_file, 'wb') as f:
        pickle.dump({
            'timestamp': datetime.now(),
            'value': value
        }, f)

# -------------------- Blogger API Functions --------------------
def get_blogger_service():
    """Get authenticated Blogger service"""
    try:
        creds = Credentials(
            token=None,
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/blogger"]
        )
        
        # Refresh the token
        creds.refresh(Request())
        
        # Build the service
        service = build('blogger', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"❌ Error authenticating with Blogger: {e}")
        return None

def post_to_blogger(title, content, labels=None):
    """Post directly to Google Blogger"""
    if labels is None:
        labels = ['AI Generated', 'Trending', 'Daily Post']
    
    try:
        service = get_blogger_service()
        if not service:
            return False
        
        # Prepare the post content with HTML formatting
        post_content = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.8; max-width: 800px; margin: 0 auto;">
            <article>
                {content.replace(chr(10), '<br>')}
            </article>
            <hr style="margin: 40px 0 20px; border: 0; border-top: 1px solid #eaeaea;">
            <p style="color: #666; font-size: 0.9em; font-style: italic;">
                This post was automatically generated on {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}
                <br>Source: Trending topics from various news sources
            </p>
        </div>
        """
        
        # Create the post body
        post_body = {
            "kind": "blogger#post",
            "title": title,
            "content": post_content,
            "labels": labels
        }
        
        # Insert the post
        posts = service.posts()
        request = posts.insert(blogId=BLOGGER_BLOG_ID, body=post_body)
        response = request.execute()
        
        print(f"✅ Successfully posted to Blogger!")
        print(f"📌 Post URL: {response.get('url')}")
        return True
        
    except Exception as e:
        print(f"❌ Error posting to Blogger: {e}")
        return False

# -------------------- Trending Topics --------------------
def get_trending_topics_free():
    """Get trending topics from free RSS feeds"""
    cached_topics = get_cache('trending_topics', max_age_hours=1)
    if cached_topics:
        print("📦 Using cached trending topics")
        return cached_topics
    
    print("🌐 Fetching fresh trending topics...")
    topics = []
    
    # Hacker News
    try:
        hn_feed = feedparser.parse('https://news.ycombinator.com/rss')
        for entry in hn_feed.entries[:5]:
            topics.append({
                'title': entry.title,
                'description': entry.get('summary', 'Popular tech discussion')[:200],
                'url': entry.link,
                'source': 'Hacker News'
            })
    except Exception as e:
        print(f"⚠️ Error fetching Hacker News: {e}")
    
    # Reddit
    try:
        reddit_feed = feedparser.parse('https://www.reddit.com/r/all/top/.rss?limit=5')
        for entry in reddit_feed.entries[:3]:
            topics.append({
                'title': entry.title,
                'description': f"Trending on Reddit",
                'url': entry.link,
                'source': 'Reddit'
            })
    except Exception as e:
        print(f"⚠️ Error fetching Reddit: {e}")
    
    # BBC News
    try:
        bbc_feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in bbc_feed.entries[:3]:
            topics.append({
                'title': entry.title,
                'description': entry.get('summary', 'Latest news')[:200],
                'url': entry.link,
                'source': 'BBC'
            })
    except Exception as e:
        print(f"⚠️ Error fetching BBC: {e}")
    
    # TechCrunch
    try:
        tc_feed = feedparser.parse('https://techcrunch.com/feed/')
        for entry in tc_feed.entries[:3]:
            topics.append({
                'title': entry.title,
                'description': entry.get('summary', 'Tech news')[:200],
                'url': entry.link,
                'source': 'TechCrunch'
            })
    except Exception as e:
        print(f"⚠️ Error fetching TechCrunch: {e}")
    
    # If NO topics found, create fallback topics
    if not topics:
        print("⚠️ No topics from RSS, using fallback topics")
        topics = [
            {
                'title': 'The Future of Artificial Intelligence in 2026',
                'description': 'How AI is transforming our daily lives and what to expect in the coming years',
                'url': 'https://example.com/ai-future',
                'source': 'Tech Trends'
            },
            {
                'title': 'Climate Change: Latest Innovations in Green Technology',
                'description': 'New breakthroughs in renewable energy and sustainable solutions',
                'url': 'https://example.com/climate-tech',
                'source': 'Science Daily'
            },
            {
                'title': 'Space Exploration: Missions to Mars and Beyond',
                'description': 'Latest updates on space travel and interplanetary exploration',
                'url': 'https://example.com/space',
                'source': 'Space News'
            }
        ]
    
    if topics:
        set_cache('trending_topics', topics)
        print(f"✅ Cached {len(topics)} topics")
    
    return topics

# -------------------- Generate with Ollama --------------------
def generate_with_ollama(prompt, model="phi"):
    """Generate text using local Ollama"""
    try:
        response = requests.post('http://localhost:11434/api/generate', 
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 2000
                }
            },
            timeout=300
        )
        if response.status_code == 200:
            return response.json()['response'].strip()
    except Exception as e:
        print(f"⚠️ API Error: {e}")
        # Fallback to CLI
        try:
            result = subprocess.run(
                ['ollama', 'run', model, prompt],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e2:
            print(f"⚠️ CLI Error: {e2}")
            return None
    return None

def generate_blog_post(topic):
    """Generate blog post content"""
    prompt = f"""Write a detailed, engaging blog post about this topic:

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}

Write a complete blog post with:
- An attention-grabbing introduction
- 3-4 informative paragraphs with details and examples
- A strong conclusion
- Length: 500-700 words

Make it sound like a real human wrote it. Don't mention AI.
Use natural language and keep it interesting.
Format with proper paragraphs.

Blog Post:
"""
    
    print(f"🤔 Generating post about: {topic['title']}")
    content = generate_with_ollama(prompt)
    
    if content and len(content) > 200:
        return content
    else:
        # If generation failed, return a simple fallback
        return f"""<h2>Introduction</h2>
<p>{topic['description']}</p>

<h2>Why This Matters</h2>
<p>The topic of <strong>{topic['title']}</strong> has been gaining attention recently. Understanding its implications is important for anyone interested in staying informed about current trends.</p>

<h2>Key Points to Consider</h2>
<p>Experts in the field suggest that developments in this area will continue to accelerate. Whether you're a professional or simply curious, keeping up with {topic['source']} can provide valuable insights.</p>

<h2>Looking Ahead</h2>
<p>As we move further into 2026, we can expect more innovations and discussions around {topic['title']}. Stay tuned for updates and deeper dives into related topics.</p>

<h2>Conclusion</h2>
<p>Thank you for reading this automated post. We hope it provided useful information and sparked your interest in learning more.</p>"""

# -------------------- Check if already posted today --------------------
def already_posted_today():
    """Check if we already posted today to avoid duplicates"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = CACHE_DIR / "posts_log.json"
    
    if log_file.exists():
        with open(log_file, 'r') as f:
            log = json.load(f)
            for entry in log:
                if entry['date'] == today:
                    print(f"📅 Already posted today: {entry['title']}")
                    return True
    return False

def log_post(title, blogger_url):
    """Log the post to avoid duplicates"""
    log_file = CACHE_DIR / "posts_log.json"
    log = []
    if log_file.exists():
        with open(log_file, 'r') as f:
            log = json.load(f)
    
    log.append({
        'date': datetime.now().strftime("%Y-%m-%d"),
        'time': datetime.now().strftime("%H:%M:%S"),
        'title': title,
        'url': blogger_url
    })
    
    with open(log_file, 'w') as f:
        json.dump(log[-30:], f, indent=2)

# -------------------- MAIN --------------------
def main():
    print("=" * 60)
    print("🚀 Starting Daily Blog Post Generator for Blogger")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Blog ID: {BLOGGER_BLOG_ID}")
    print("=" * 60)
    
    # Check if already posted today
    if already_posted_today():
        print("✅ Already posted today. Exiting.")
        return
    
    # Get trending topics
    print("\n🔍 Fetching trending topics...")
    topics = get_trending_topics_free()
    
    print(f"📊 Found {len(topics)} topics")
    
    # Pick a random topic
    chosen = random.choice(topics)
    print(f"🎯 Selected: {chosen['title']}")
    print(f"📌 Source: {chosen['source']}")
    
    # Generate blog post
    print("\n✍️ Generating blog post with AI...")
    content = generate_blog_post(chosen)
    
    if content:
        print("✅ Content generated successfully!")
        
        # Post to Blogger
        print("\n📤 Posting to Blogger...")
        success = post_to_blogger(chosen['title'], content, ['AI Generated', chosen['source'].replace(' ', '-')])
        
        if success:
            print("\n✨ MISSION COMPLETE! Blog post is live on Blogger!")
        else:
            # Fallback: Save locally
            print("\n⚠️ Blogger post failed, saving locally...")
            os.makedirs("_posts", exist_ok=True)
            filename = f"_posts/{datetime.now().strftime('%Y-%m-%d')}-{chosen['title'][:50].replace(' ', '-')}.md"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# {chosen['title']}\n\n{content}")
            print(f"✅ Saved locally: {filename}")
    else:
        print("❌ Failed to generate content.")

if __name__ == "__main__":
    main()
