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

# -------------------- Cache Setup --------------------
CACHE_DIR = Path(".blog-cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache(key, max_age_hours=24):
    """Get item from cache if not expired"""
    cache_file = CACHE_DIR / f"{key}.pkl"
    if cache_file.exists():
        with open(cache_file, 'rb') as f:
            data = pickle.load(f)
            timestamp = data.get('timestamp')
            if timestamp and datetime.now() - timestamp < timedelta(hours=max_age_hours):
                return data.get('value')
    return None

def set_cache(key, value):
    """Save item to cache"""
    cache_file = CACHE_DIR / f"{key}.pkl"
    with open(cache_file, 'wb') as f:
        pickle.dump({
            'timestamp': datetime.now(),
            'value': value
        }, f)

def get_topic_hash(topic):
    """Create a unique hash for a topic to avoid duplicates"""
    text = f"{topic['title']}{topic['url']}".encode('utf-8')
    return hashlib.md5(text).hexdigest()

def is_topic_used(topic_hash):
    """Check if we've already written about this topic"""
    used_file = CACHE_DIR / "used_topics.txt"
    if used_file.exists():
        with open(used_file, 'r') as f:
            used = set(line.strip() for line in f)
            return topic_hash in used
    return False

def mark_topic_used(topic_hash):
    """Mark a topic as used"""
    used_file = CACHE_DIR / "used_topics.txt"
    with open(used_file, 'a') as f:
        f.write(f"{topic_hash}\n")

# -------------------- Free Trending Sources (Cached) --------------------
def get_trending_topics_free():
    """Get trending topics from free RSS feeds with caching"""
    
    # Try cache first
    cached_topics = get_cache('trending_topics', max_age_hours=1)  # Cache for 1 hour
    if cached_topics:
        print("📦 Using cached trending topics")
        return cached_topics
    
    print("🌐 Fetching fresh trending topics...")
    topics = []
    
    # Source 1: Hacker News (tech trends)
    try:
        hn_feed = feedparser.parse('https://news.ycombinator.com/rss')
        for entry in hn_feed.entries[:5]:
            topics.append({
                'title': entry.title,
                'description': entry.get('summary', 'Popular tech discussion')[:200],
                'url': entry.link,
                'source': 'Hacker News',
                'score': entry.get('score', 100)  # Default score
            })
    except Exception as e:
        print(f"⚠️ Error fetching Hacker News: {e}")
    
    # Source 2: Reddit (r/all/top/.rss)
    try:
        reddit_feed = feedparser.parse('https://www.reddit.com/r/all/top/.rss?limit=5')
        for entry in reddit_feed.entries[:3]:
            topics.append({
                'title': entry.title,
                'description': f"Trending on Reddit with {entry.get('media:statistics', {}).get('views', 'many')} views",
                'url': entry.link,
                'source': 'Reddit',
                'score': entry.get('score', 80)
            })
    except Exception as e:
        print(f"⚠️ Error fetching Reddit: {e}")
    
    # Source 3: BBC News RSS
    try:
        bbc_feed = feedparser.parse('http://feeds.bbci.co.uk/news/rss.xml')
        for entry in bbc_feed.entries[:3]:
            topics.append({
                'title': entry.title,
                'description': entry.get('summary', 'Latest news')[:200],
                'url': entry.link,
                'source': 'BBC',
                'score': 90
            })
    except Exception as e:
        print(f"⚠️ Error fetching BBC: {e}")
    
    # Source 4: TechCrunch
    try:
        tc_feed = feedparser.parse('https://techcrunch.com/feed/')
        for entry in tc_feed.entries[:3]:
            topics.append({
                'title': entry.title,
                'description': entry.get('summary', 'Tech news')[:200],
                'url': entry.link,
                'source': 'TechCrunch',
                'score': 85
            })
    except Exception as e:
        print(f"⚠️ Error fetching TechCrunch: {e}")
    
    # Cache the results
    if topics:
        set_cache('trending_topics', topics)
        print(f"✅ Cached {len(topics)} topics")
    
    return topics

# -------------------- LLM Interaction (Local Ollama) --------------------
def generate_with_ollama(prompt, model="phi", max_retries=2):
    """Generate text using local Ollama instance with retries"""
    
    for attempt in range(max_retries):
        try:
            # Try using the Ollama API first (faster)
            response = requests.post('http://localhost:11434/api/generate', 
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 1500,
                        "top_k": 40,
                        "top_p": 0.9
                    }
                },
                timeout=300
            )
            
            if response.status_code == 200:
                return response.json()['response'].strip()
            else:
                # Fallback to CLI
                result = subprocess.run(
                    ['ollama', 'run', model, prompt],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    return result.stdout.strip()
                    
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print("🔄 Retrying...")
                continue
    
    return None

def generate_blog_post(topic):
    """Generate a complete blog post using the LLM"""
    
    # Check if we already generated this topic
    topic_hash = get_topic_hash(topic)
    if is_topic_used(topic_hash):
        print(f"⏭️ Already wrote about this topic, skipping...")
        return None
    
    # Check cache for similar posts
    cached_post = get_cache(f"post_{topic_hash}", max_age_hours=24*7)  # Cache for a week
    if cached_post:
        print("📦 Using cached generated post")
        return cached_post
    
    prompt = f"""Write a fresh, engaging blog post about this trending topic:

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}
DATE: {datetime.now().strftime('%B %d, %Y')}

Requirements:
- Write 400-600 words
- Include an introduction, 3-4 paragraphs, and a conclusion
- Make it informative and engaging
- Use current, up-to-date information
- Don't mention that you're an AI
- Write in a natural, human tone
- Include relevant facts and context
- Make it unique and not generic

Blog Post:
"""
    
    print(f"🤔 Generating post about: {topic['title']}")
    content = generate_with_ollama(prompt)
    
    if content and len(content) > 200:
        # Cache the generated content
        set_cache(f"post_{topic_hash}", content)
        mark_topic_used(topic_hash)
        return content
    else:
        print("❌ Generated content was too short or failed.")
        return None

# -------------------- Save Post --------------------
def save_post(topic, content):
    """Save the generated post as a markdown file"""
    
    # Create filename from title
    slug = topic['title'].lower()[:50]
    slug = ''.join(c for c in slug if c.isalnum() or c == ' ').replace(' ', '-')
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"_posts/{date_str}-{slug}.md"
    
    # Check if file already exists
    if os.path.exists(filename):
        print(f"⚠️ File {filename} already exists, skipping...")
        return None
    
    # Create front matter with metadata
    front_matter = f"""---
layout: post
title: "{topic['title']}"
date: {date_str} {datetime.now().strftime('%H:%M:%S')} +0000
categories: [trending, {topic['source'].lower().replace(' ', '-')}]
source: {topic['url']}
source_name: {topic['source']}
generated: {datetime.now().isoformat()}
---

"""
    
    # Write file
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(front_matter + content)
    
    print(f"✅ Saved: {filename}")
    
    # Log the post for future reference
    log_entry = {
        'filename': filename,
        'title': topic['title'],
        'source': topic['source'],
        'date': date_str,
        'hash': get_topic_hash(topic)
    }
    
    log_file = CACHE_DIR / "posts_log.json"
    if log_file.exists():
        with open(log_file, 'r') as f:
            log = json.load(f)
    else:
        log = []
    
    log.append(log_entry)
    with open(log_file, 'w') as f:
        json.dump(log[-100:], f, indent=2)  # Keep last 100 posts
    
    return filename

# -------------------- Check Posting Schedule --------------------
def should_post_today():
    """Check if we should post today (avoid duplicates)"""
    today = datetime.now().strftime("%Y-%m-%d")
    posts_dir = Path("_posts")
    
    if not posts_dir.exists():
        posts_dir.mkdir(exist_ok=True)
        return True
    
    # Check if we already posted today
    for f in posts_dir.glob(f"{today}-*.md"):
        print(f"📅 Already posted today: {f.name}")
        return False
    
    # Check post frequency from log
    log_file = CACHE_DIR / "posts_log.json"
    if log_file.exists():
        with open(log_file, 'r') as f:
            log = json.load(f)
            if len(log) > 0:
                last_post = datetime.fromisoformat(log[-1]['date'])
                if datetime.now() - last_post < timedelta(hours=20):
                    print("⏰ Too soon since last post")
                    return False
    
    return True

# -------------------- Main --------------------
def main():
    print("=" * 50)
    print("🚀 Starting daily blog post generation...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # Check if we should post
    if not should_post_today():
        print("✅ Posting not needed today. Exiting.")
        return
    
    # Get trending topics
    print("\n🔍 Fetching trending topics...")
    topics = get_trending_topics_free()
    
    if not topics:
        print("❌ No topics found.")
        return
    
    print(f"📊 Found {len(topics)} trending topics")
    
    # Filter out already used topics
    fresh_topics = []
    for topic in topics:
        if not is_topic_used(get_topic_hash(topic)):
            fresh_topics.append(topic)
    
    if not fresh_topics:
        print("⚠️ All topics have been used before. Using newest ones anyway.")
        fresh_topics = topics[:3]
    
    print(f"✨ {len(fresh_topics)} fresh topics available")
    
    # Try topics until we get a good generation
    for topic in fresh_topics[:3]:  # Try up to 3 topics
        print(f"\n🎯 Selected: {topic['title']} from {topic['source']}")
        
        # Generate blog post
        content = generate_blog_post(topic)
        
        if content and len(content) > 200:
            filename = save_post(topic, content)
            if filename:
                print("\n✨ Blog post generated and saved!")
                
                # Show preview
                print("\n--- Preview ---")
                preview = content[:300] + "..." if len(content) > 300 else content
                print(preview)
                print("-" * 50)
                
                # Success! Exit loop
                return
            else:
                print("⚠️ Failed to save post, trying next topic...")
        else:
            print("⚠️ Generation failed, trying next topic...")
    
    print("\n❌ Failed to generate a valid post after trying multiple topics.")

if __name__ == "__main__":
    main()
