🤖 AI Blogger – Fully Automated Blog Posting System

This repository contains a complete automation system that generates and publishes high‑quality blog posts to your Blogger blog using AI. It runs on GitHub Actions (free for public repositories) and uses Ollama (with optional AirLLM) to create engaging, long‑form content. The system also fetches relevant images, adds your logo, improves SEO, and notifies Google for faster indexing.

✨ Features

6 posts daily at optimal reader engagement times (configurable).
1500–2000 word articles with a clear structure (synopsis, introduction, analysis, conclusion).
AI models: Uses tinyllama (fast) by default, falls back to phi or llama3:8b if needed.
Images: Automatically extracts images from RSS feeds, falls back to Unsplash or Picsum.
Logo: Adds your custom logo (centered) at the bottom of every post.
SEO enhancements:

Meta descriptions from the AI‑generated summary.
Internal links to related posts.
Google sitemap ping after each post.
Optional Google Search Console submission via Indexing API.
Local backups: Every generated post is saved as a Markdown file and uploaded as a GitHub Actions artifact.
Fully configurable: Modify prompts, post length, models, and schedules easily.

📋 Prerequisites

Before you begin, make sure you have:

A GitHub account (free).
A Blogger blog (create one at blogger.com).
Your Blogger Blog ID (found in Settings → Basic → Blog ID).
Google Cloud Project with Blogger API enabled and OAuth 2.0 credentials (see setup guide).
(Optional) Google Search Console service account for automatic indexing (see guide).
A logo image (PNG format) if you want branding.

🚀 Quick Start

1. Fork or Clone This Repository

bash
git clone https://github.com/adavidjulius/Automatic-Blogger-Poster.git
cd Automatic-Blogger-Poster
2. Add Required Files to Your Repository

Place your logo as logo.png in the root folder.
Ensure the following files exist (they are already in the repo):

.github/workflows/daily-blog.yml – the GitHub Actions workflow.
scripts/generate_post.py – the main Python script.
requirements.txt – Python dependencies.
3. Configure GitHub Secrets

Go to your repository Settings → Secrets and variables → Actions and add the following secrets:

Secret Name	Description
BLOGGER_BLOG_ID	Your Blogger blog ID (a number, e.g., 6965563738161457805).
GOOGLE_CLIENT_ID	OAuth 2.0 Client ID from Google Cloud Console.
GOOGLE_CLIENT_SECRET	OAuth 2.0 Client Secret.
GOOGLE_REFRESH_TOKEN	Refresh token for Blogger API (obtained via OAuth 2.0 Playground).
GSC_SERVICE_ACCOUNT_JSON	(Optional) Full JSON key of your Google Search Console service account.
4. Customize the Workflow (Optional)

Edit .github/workflows/daily-blog.yml to change posting times (cron syntax) or any other settings.

5. Push and Wait

Commit and push all changes to your default branch (usually main). The workflow will run automatically at the scheduled times. You can also trigger it manually from the Actions tab.

🔧 How It Works

GitHub Actions triggers the workflow at the scheduled times (or manually).
Ollama is installed and started on the runner.
The script generate_post.py:

Fetches trending topics from RSS feeds (Hacker News, BBC, TechCrunch).
Selects a random topic.
Extracts an image from the feed (if available) or uses Unsplash/Picsum.
Generates a 1500‑2000 word blog post using Ollama (primary: tinyllama, fallbacks: phi, llama3:8b).
Creates a summary for meta description and internal linking.
Publishes the post to Blogger via the API.
Pings Google with the sitemap URL.
(Optional) Submits the new URL to Google Search Console.
Saves a local backup in the _posts/ folder.
The post is also uploaded as a GitHub Actions artifact for safekeeping.

🎨 Customization

Changing Post Length

In generate_post.py, modify the num_predict parameter in the API call (e.g., 2048 for ~1500 words). Also adjust the prompt's length instructions.

Switching AI Models

Change the OLLAMA_PRIMARY, OLLAMA_SECONDARY, and OLLAMA_TERTIARY variables at the top of the script. Popular models:

tinyllama (fast, 1.1B)
phi (2.7B)
llama3:8b (8B, better quality but slower)
mistral:7b (7B)
Adding More RSS Sources

Edit the sources list in get_trending_topics() to include your preferred feeds.

Adjusting Posting Schedule

Modify the cron lines in .github/workflows/daily-blog.yml. The current schedule is:

30 3 * * * → 03:30 UTC
0 7 * * * → 07:00 UTC
30 12 * * * → 12:30 UTC
0 13 * * * → 13:00 UTC
30 16 * * * → 16:30 UTC
0 19 * * * → 19:00 UTC

🔑 Setting Up Google OAuth 2.0 for Blogger

Go to the Google Cloud Console.
Create a new project (or select an existing one).
Enable the Blogger API v3.
Go to APIs & Services → Credentials.
Click + CREATE CREDENTIALS → OAuth client ID.
Choose Web application, give it a name, and add https://developers.google.com/oauthplayground as an Authorized redirect URI.
Note your Client ID and Client Secret.
Visit the OAuth 2.0 Playground.

Click the gear icon, check "Use your own OAuth credentials", and enter your Client ID and Secret.
In the left panel, select Blogger API v3 and choose the scope https://www.googleapis.com/auth/blogger.
Click Authorize APIs, log in with your blog owner account, and grant permission.
Click Exchange authorization code for tokens.
Copy the refresh token.
Now add these values as GitHub secrets.

📈 (Optional) Google Search Console Integration

To automatically submit new posts to Google for faster indexing:

In the Google Cloud Console, enable the Indexing API.
Create a service account (IAM & Admin → Service Accounts) and download its JSON key.
Add the service account email as an owner in your Search Console property (Settings → Users and permissions).
Add the entire JSON key as the GitHub secret GSC_SERVICE_ACCOUNT_JSON.

🐛 Troubleshooting

Issue	Solution
Workflow fails with "No such file or directory"	Ensure scripts/generate_post.py exists in your repository.
Model generation times out	Increase TIMEOUT_SECONDS in the script, or use a smaller model like tinyllama.
Google ping returns 404	The sitemap URL may be incorrect. The script auto‑detects the correct one, but you can manually set SITEMAP_URL in the script.
Search Console API returns 401	Verify that the service account email is added as an owner in Search Console and that the JSON secret is correctly pasted.
AirLLM not installed	The workflow installs AirLLM; check the "Install Python dependencies" step logs for errors. If it fails, the script falls back to Ollama.

📄 License

This project is open source and available under the MIT License.
