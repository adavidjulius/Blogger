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
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# -------------------- BLOGGER CONFIGURATION --------------------
BLOGGER_BLOG_ID = os.getenv("6965563738161457805")
GOOGLE_CLIENT_ID = os.getenv("405755279071-4vnbgocint5n006qj6i31e589q17l6un.apps.googleusercontent.com")
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
        service = build('blogger', 'v3', credentials=creds, developerKey=GOOGLE_API_KEY)
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
            return False, "Authentication failed"
        
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
        return True, response.get('url')
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error posting to Blogger: {error_msg}")
        return False, error_msg

# -------------------- Trending Topics --------------------
def get_trending_topics():
    """Get trending topics from free RSS feeds"""
    cached_topics = get_cache('trending_topics', max_age_hours=1)
    if cached_topics:
        print("📦 Using cached trending topics")
        return cached_topics
    
    print("🌐 Fetching fresh trending topics...")
    topics = []
    sources = [
        ('https://news.ycombinator.com/rss', 'Hacker News', 5),
        ('https://www.reddit.com/r/all/top/.rss?limit=5', 'Reddit', 3),
        ('http://feeds.bbci.co.uk/news/rss.xml', 'BBC', 3),
        ('https://techcrunch.com/feed/', 'TechCrunch', 3),
        ('https://www.wired.com/feed/rss', 'Wired', 3)
    ]
    
    for url, source_name, limit in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
                topics.append({
                    'title': entry.title,
                    'description': entry.get('summary', '')[:200],
                    'url': entry.link,
                    'source': source_name
                })
        except Exception as e:
            print(f"⚠️ Error fetching {source_name}: {e}")
    
    # Fallback topics if none found
    if not topics:
        print("⚠️ No topics from RSS, using fallback topics")
        topics = [
            {'title': 'The Future of Artificial Intelligence in 2026', 'description': 'How AI is transforming our daily lives', 'source': 'Tech Trends', 'url': '#'},
            {'title': 'Climate Change: Latest Innovations in Green Technology', 'description': 'New breakthroughs in renewable energy', 'source': 'Science Daily', 'url': '#'},
            {'title': 'Space Exploration: Missions to Mars and Beyond', 'description': 'Latest updates on space travel', 'source': 'Space News', 'url': '#'},
            {'title': 'Digital Privacy: Protecting Your Data in 2026', 'description': 'Essential tips for keeping your information secure', 'source': 'Security Weekly', 'url': '#'},
            {'title': 'The Rise of Remote Work: How Companies Are Adapting', 'description': 'Work-from-home trends', 'source': 'Business Insider', 'url': '#'},
            {'title': 'Breakthroughs in Medical Technology', 'description': 'New treatments and health innovations', 'source': 'Health News', 'url': '#'},
            {'title': 'Electric Vehicles: The Road Ahead', 'description': 'Latest models and battery technology', 'source': 'Auto News', 'url': '#'},
            {'title': 'Cryptocurrency and Blockchain Updates', 'description': 'Market trends and developments', 'source': 'Finance Today', 'url': '#'},
            {'title': 'Gaming Industry: New Releases and Trends', 'description': 'Latest games and gaming technology', 'source': 'GameSpot', 'url': '#'}
        ]
    
    if topics:
        set_cache('trending_topics', topics)
        print(f"✅ Found {len(topics)} topics")
    
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
    
    # Ultimate fallback
    return f"""<h2>Introduction</h2>
<p>Today we're discussing an important topic that's been making waves recently.</p>

<h2>Key Points</h2>
<p>The developments in this area are worth paying attention to. Experts suggest that we'll see continued innovation and change.</p>

<h2>Conclusion</h2>
<p>Stay tuned for more updates on this and other trending topics!</p>"""

def generate_blog_post(topic):
    """Generate blog post content"""
    prompt = f"""Write a detailed, engaging blog post about this topic:

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

Write a complete blog post with:
- An attention-grabbing introduction
- 3-4 informative paragraphs with details and examples
- A strong conclusion
- Length: 500-700 words

Make it sound professional and interesting.

Blog Post:
"""
    
    print(f"🤔 Generating post about: {topic['title']}")
    return generate_with_ollama(prompt)

# -------------------- Check if already posted today --------------------
def already_posted_today():
    """Check if we already posted today"""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = CACHE_DIR / "posts_log.json"
    
    if log_file.exists():
        with open(log_file, 'r') as f:
            log = json.load(f)
            for entry in log:
                if entry.get('date') == today:
                    print(f"📅 Already posted today")
                    return True
    return False

def log_post(title, url):
    """Log the post"""
    log_file = CACHE_DIR / "posts_log.json"
    log = []
    if log_file.exists():
        with open(log_file, 'r') as f:
            log = json.load(f)
    
    log.append({
        'date': datetime.now().strftime("%Y-%m-%d"),
        'time': datetime.now().strftime("%H:%M:%S"),
        'title': title,
        'url': url
    })
    
    with open(log_file, 'w') as f:
        json.dump(log[-30:], f, indent=2)

# -------------------- MAIN --------------------
def main():
    print("=" * 60)
    print("🚀 Daily Blog Post Generator for Blogger")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Blog ID: {BLOGGER_BLOG_ID}")
    print("=" * 60)
    
    # Check if already posted
    if already_posted_today():
        print("✅ Already posted today. Exiting.")
        return
    
    # Get topics
    print("\n🔍 Fetching trending topics...")
    topics = get_trending_topics()
    print(f"📊 Found {len(topics)} topics")
    
    # Pick random topic
    chosen = random.choice(topics)
    print(f"🎯 Selected: {chosen['title']}")
    print(f"📌 Source: {chosen['source']}")
    
    # Generate content
    print("\n✍️ Generating blog post...")
    content = generate_blog_post(chosen)
    
    if content:
        print("✅ Content generated!")
        
        # Post to Blogger
        print("\n📤 Posting to Blogger...")
        success, result = post_to_blogger(chosen['title'], content, 
                                          ['AI Generated', chosen['source'].replace(' ', '-')])
        
        if success:
            log_post(chosen['title'], result)
            print("\n✨ SUCCESS! Blog post is live!")
        else:
            # Save locally as backup
            filename = f"_posts/{datetime.now().strftime('%Y-%m-%d')}-{chosen['title'][:50].replace(' ', '-')}.md"
            os.makedirs("_posts", exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"# {chosen['title']}\n\n{content}")
            print(f"✅ Saved locally: {filename}")
            print(f"⚠️ Blogger error: {result}")
    else:
        print("❌ Failed to generate content")

if __name__ == "__main__":
    main()
