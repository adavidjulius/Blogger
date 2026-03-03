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

# -------------------- BLOGGER SETUP --------------------
BLOGGER_ID = "6965563738161457805"  # Replace with your actual Blogger ID
BLOG_URL = "https://draft.blogger.com/blog/posts/6965563738161457805"  # Replace with your blog URL

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
    
    if topics:
        set_cache('trending_topics', topics)
    
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
                    "num_predict": 1500
                }
            },
            timeout=300
        )
        if response.status_code == 200:
            return response.json()['response'].strip()
    except Exception as e:
        print(f"⚠️ Error: {e}")
        # Fallback to CLI
        try:
            result = subprocess.run(
                ['ollama', 'run', model, prompt],
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.stdout.strip()
        except:
            return None
    return None

def generate_blog_post(topic):
    """Generate blog post content"""
    prompt = f"""Write a blog post about this trending topic:

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}

Write 400-600 words with introduction, paragraphs, and conclusion.
Make it engaging and informative.
Don't mention AI.
Use natural language.

Blog Post:
"""
    
    print(f"🤔 Generating post about: {topic['title']}")
    return generate_with_ollama(prompt)

# -------------------- POST TO BLOGGER --------------------
def post_to_blogger(title, content, labels=None):
    """Post directly to Google Blogger"""
    if labels is None:
        labels = ['AI Generated', 'Trending', 'Daily Post']
    
    # Prepare the post content
    post_content = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6;">
        {content.replace(chr(10), '<br>')}
        <br><br>
        <hr>
        <p style="color: #666; font-size: 0.9em;">
            This post was automatically generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}
            <br>Source: Trending topics from various news sources
        </p>
    </div>
    """
    
    # For now, save to file (we'll implement actual Blogger API next)
    post_file = CACHE_DIR / f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(post_file, 'w', encoding='utf-8') as f:
        f.write(f"<h1>{title}</h1>\n{post_content}")
    
    print(f"📝 Post saved locally: {post_file}")
    print("\n🔴 NOTE: To auto-post to Blogger, we need to set up Google API")
    print("For now, the post is saved and you can manually copy it to Blogger")
    
    return post_file

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

def log_post(title, post_file):
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
        'file': str(post_file)
    })
    
    with open(log_file, 'w') as f:
        json.dump(log[-30:], f, indent=2)  # Keep last 30 days

# -------------------- MAIN --------------------
def main():
    print("=" * 50)
    print("🚀 Starting Daily Blog Post Generator for Blogger")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Blog: {BLOG_URL}")
    print("=" * 50)
    
    # Check if already posted today
    if already_posted_today():
        print("✅ Already posted today. Exiting.")
        return
    
    # Get trending topics
    print("\n🔍 Fetching trending topics...")
    topics = get_trending_topics_free()
    
    if not topics:
        print("❌ No topics found.")
        return
    
    print(f"📊 Found {len(topics)} trending topics")
    
    # Pick a random topic
    chosen = random.choice(topics[:10])
    print(f"🎯 Selected: {chosen['title']}")
    print(f"📌 Source: {chosen['source']}")
    
    # Generate blog post
    content = generate_blog_post(chosen)
    
    if content and len(content) > 200:
        # Post to Blogger
        print("\n📤 Posting to Blogger...")
        post_file = post_to_blogger(chosen['title'], content)
        
        # Log the post
        log_post(chosen['title'], post_file)
        
        print("\n✨ Success!")
        print("\n--- Preview ---")
        print(content[:300] + "...")
        print("-" * 50)
        
        print(f"\n✅ Post saved! You can find it in: {post_file}")
        print("🔗 Your Blogger dashboard: https://www.blogger.com")
    else:
        print("❌ Failed to generate content.")

if __name__ == "__main__":
    main()
