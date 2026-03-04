#!/usr/bin/env python3
"""
Blogger Auto-Poster with Stable Diffusion Images
- Uses Ollama for content generation
- Uses dusty-nv/small-stable-diffusion for AI image generation
- Falls back to Unsplash if Stable Diffusion fails
- Beautiful formatting with multiple fallbacks
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

# Google API
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

# ==================== READ SECRETS FROM ENVIRONMENT ====================
BLOGGER_BLOG_ID = os.getenv("BLOGGER_BLOG_ID")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# ==================== CONFIG ====================
PRIMARY_MODEL = "llama3:8b"
FALLBACK_MODEL = "phi"

# Path to Stable Diffusion
SD_PATH = "small-stable-diffusion"

# ==================== SETUP ====================
CACHE_DIR = Path(".blog-cache")
POSTS_DIR = Path("_posts")
IMAGES_DIR = Path("images")
CACHE_DIR.mkdir(exist_ok=True)
POSTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

def log_error(step, error, details=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n❌ ERROR at {timestamp}")
    print(f"   Step: {step}")
    print(f"   Error: {error}")
    if details:
        print(f"   Details: {details}")
    print(f"   Traceback: {traceback.format_exc()}")

# ==================== STABLE DIFFUSION IMAGE GENERATION ====================
def generate_image_with_sd(prompt, output_path):
    """
    Generate image using dusty-nv/small-stable-diffusion
    """
    try:
        print(f"🎨 Generating image with Stable Diffusion...")
        
        # Create a simple Python script to run Stable Diffusion
        sd_script = f"""
import sys
sys.path.append('{SD_PATH}')
from diffusers import StableDiffusionPipeline
import torch
from PIL import Image

# Load model
pipe = StableDiffusionPipeline.from_pretrained(
    "runwayml/stable-diffusion-v1-5",
    torch_dtype=torch.float16,
    safety_checker=None
)
pipe = pipe.to("cuda")

# Generate image
prompt = "{prompt}"
image = pipe(prompt, num_inference_steps=30).images[0]

# Save image
image.save("{output_path}")
print("✅ Image generated and saved")
"""
        
        # Write script to file
        script_path = CACHE_DIR / "generate_image.py"
        with open(script_path, 'w') as f:
            f.write(sd_script)
        
        # Run the script
        result = subprocess.run(
            ['python', str(script_path)],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Image saved to {output_path}")
            return True
        else:
            print(f"⚠️ SD error: {result.stderr[:200]}")
            return False
            
    except Exception as e:
        print(f"⚠️ Stable Diffusion error: {e}")
        return False

def get_unsplash_image(topic_title):
    """Fallback to Unsplash if SD fails"""
    try:
        # Extract keywords from title (first 3 meaningful words)
        words = topic_title.split()[:3]
        clean_words = []
        for w in words:
            clean = ''.join(c for c in w if c.isalnum())
            if clean and len(clean) > 2:
                clean_words.append(clean)
        
        if not clean_words:
            clean_words = ["technology", "news"]
        
        keywords = '+'.join(clean_words)
        
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
    """
    Create HTML for image – tries Stable Diffusion first, then Unsplash
    """
    # Try Stable Diffusion first
    image_filename = f"sd_image_{int(time.time())}.png"
    image_path = IMAGES_DIR / image_filename
    
    # Create prompt from title
    sd_prompt = f"Professional blog header image about {title}, high quality, detailed, 4k"
    
    success = generate_image_with_sd(sd_prompt, str(image_path))
    
    if success:
        # Convert to base64 and embed
        try:
            with open(image_path, 'rb') as f:
                img_data = f.read()
                img_b64 = base64.b64encode(img_data).decode('utf-8')
            
            return f'''
            <div style="margin-bottom:30px; text-align:center;">
                <img src="data:image/png;base64,{img_b64}" alt="{title}"
                     style="width:100%; max-width:900px; height:auto; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.15);">
                <p style="color:#777; font-size:0.8em;">🎨 AI-generated by Stable Diffusion</p>
            </div>
            '''
        except Exception as e:
            print(f"⚠️ Base64 conversion error: {e}")
    
    # Fallback to Unsplash
    img_url = get_unsplash_image(title)
    if img_url:
        return f'''
        <div style="margin-bottom:30px; text-align:center;">
            <img src="{img_url}" alt="{title}"
                 style="width:100%; max-width:900px; height:auto; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.15);">
            <p style="color:#777; font-size:0.8em;">📸 Photo from Unsplash</p>
        </div>
        '''
    
    # Ultimate fallback – gradient banner
    gradients = [
        'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
        'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
        'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)'
    ]
    gradient = random.choice(gradients)
    
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
        print("🔑 Need new refresh token from OAuth Playground.")
        return None
    except Exception as e:
        log_error("Authentication", str(e))
        return None

def post_to_blogger(title, content, labels=None):
    if labels is None:
        labels = ['AI Generated', 'Trending', 'StableDiffusion']
    
    service = get_blogger_service()
    if not service:
        return False, "Auth failed"

    # Generate and add image
    print("\n🖼️ Creating image for post...")
    image_html = create_image_html(title)
    
    full_content = image_html + content.replace('\n', '<br>')

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
    ]
    
    for url, name, limit in sources:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit]:
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
            {'title': 'The Future of AI', 'description': 'How AI is transforming our world', 'source': 'Tech'},
            {'title': 'Climate Tech Innovations', 'description': 'Breakthroughs in green energy', 'source': 'Science'},
            {'title': 'Space Exploration Updates', 'description': 'New missions to the Moon and Mars', 'source': 'Space'}
        ]
    
    random.shuffle(topics)
    return topics

# ==================== GENERATE WITH OLLAMA ====================
def generate_with_ollama(prompt, model=PRIMARY_MODEL):
    """Generate text using Ollama"""
    
    # Try API
    try:
        resp = requests.post('http://localhost:11434/api/generate',
                              json={
                                  "model": model,
                                  "prompt": prompt,
                                  "stream": False,
                                  "options": {
                                      "temperature": 0.8,
                                      "num_predict": 1200
                                  }
                              },
                              timeout=300)
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
            capture_output=True, text=True, timeout=300
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
    prompt = f"""Write a detailed, engaging blog post about:

TITLE: {topic['title']}
DESCRIPTION: {topic['description']}
SOURCE: {topic['source']}

Write 400-500 words with:
- An engaging introduction
- 3-4 informative paragraphs
- A strong conclusion

Make it professional and interesting.

POST:
"""
    
    content = generate_with_ollama(prompt)
    
    if content:
        return content
    
    # Fallback content
    return f"""
<h2>Introduction</h2>
<p>Today we're discussing <strong>{topic['title']}</strong>. This topic has been generating significant interest recently.</p>

<h2>Key Points</h2>
<p>{topic['description']}</p>

<h2>Conclusion</h2>
<p>Thank you for reading. More updates coming soon.</p>
"""

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
    print("🚀 AI BLOGGER – Stable Diffusion Edition")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # Check secrets
    missing = []
    if not BLOGGER_BLOG_ID:
        missing.append("BLOGGER_BLOG_ID")
    if not GOOGLE_CLIENT_ID:
        missing.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET:
        missing.append("GOOGLE_CLIENT_SECRET")
    if not GOOGLE_REFRESH_TOKEN:
        missing.append("GOOGLE_REFRESH_TOKEN")
    
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

    # Generate content
    print("\n✍️ Generating content with Llama 3...")
    content = generate_blog_post(topic)

    # Save backup
    local_file = save_local_post(topic['title'], content)

    # Post with image
    print("\n📤 Posting to Blogger with Stable Diffusion image...")
    success, result = post_to_blogger(
        topic['title'], 
        content,
        labels=['AI Generated', topic['source'].replace(' ', '-'), 'StableDiffusion']
    )

    print("\n" + "="*70)
    if success:
        print(f"✨ SUCCESS! Post published!")
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
