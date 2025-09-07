import asyncio
import os
import json
from playwright.async_api import async_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheets setup using environment variables
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Create credentials from environment variable
def get_google_credentials():
    credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if not credentials_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable not set")
    
    credentials_dict = json.loads(credentials_json)
    return ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, SCOPE)

CREDS = get_google_credentials()
CLIENT = gspread.authorize(CREDS)

# Replace with your spreadsheet name
SHEET = CLIENT.open("LinkedIn Jobs").sheet1

LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search-results/?distance=25.0&f_TPR=r3600&geoId=102713980&keywords=software%20engineer&origin=SEMANTIC_SEARCH_HISTORY"

async def scrape_jobs(playwright):
    """Scrapes jobs once and saves results to Google Sheets."""
    try:
        browser = await playwright.chromium.launch(
            headless=True,  # headless for GitHub Actions
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        )
        print("✅ Browser launched successfully")
    except Exception as e:
        print(f"❌ Failed to launch browser: {e}")
        # Try with minimal args as fallback
        try:
            browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'])
            print("✅ Browser launched with minimal args")
        except Exception as e2:
            print(f"❌ Browser launch failed completely: {e2}")
            raise
    
    # Load LinkedIn state from environment variable
    linkedin_state = os.getenv('LINKEDIN_STATE_JSON')
    if not linkedin_state:
        raise ValueError("LINKEDIN_STATE_JSON environment variable not set")
    
    # Write the state to a temporary file
    with open('linkedin_state.json', 'w') as f:
        f.write(linkedin_state)
    
    context = await browser.new_context(
        storage_state="linkedin_state.json",
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1920, 'height': 1080},
        extra_http_headers={
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    )
    page = await context.new_page()

    # Add extra stealth measures
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });
        
        window.chrome = {
            runtime: {},
        };
    """)

    await page.goto(LINKEDIN_JOBS_URL, timeout=60000)
    
    # Wait a bit longer and check if we're on the right page
    await page.wait_for_timeout(5000)
    
    current_url = page.url
    print(f"Current URL: {current_url}")
    
    # Take a screenshot for debugging
    try:
        await page.screenshot(path="debug_main_page.png")
        print("📸 Screenshot saved: debug_main_page.png")
    except:
        pass
    
    # Check if we got redirected to a different page
    if "user-agreement" in current_url or "legal" in current_url or "checkpoint" in current_url:
        print("⚠️ LinkedIn detected automation, trying to navigate back...")
        await page.goto(LINKEDIN_JOBS_URL, timeout=60000)
        await page.wait_for_timeout(5000)
        current_url = page.url
        print(f"New URL after retry: {current_url}")
    
    # Check if we're actually on a jobs page
    page_title = await page.title()
    page_content = await page.content()
    
    if "user-agreement" in page_content or "legal" in page_content or "We're experiencing some" in page_content:
        print("❌ LinkedIn is blocking access. The session may be expired or invalid.")
        print("💡 Try running test.py locally to refresh the LinkedIn session")
        await browser.close()
        return
    
    print(f"Page title: {page_title}")
    
    # Debug: Print page title to confirm we're on the right page
    title = await page.title()
    print(f"Page title: {title}")
    
    # Wait for job listings to load - try multiple possible selectors
    try:
        await page.wait_for_selector(".jobs-search-results__list-item", timeout=10000)
        jobs = await page.query_selector_all(".jobs-search-results__list-item")
        print(f"✅ Found {len(jobs)} jobs using .jobs-search-results__list-item")
    except:
        print("❌ .jobs-search-results__list-item not found, trying alternative selector...")
        try:
            await page.wait_for_selector("[data-view-name='job-card']", timeout=10000)
            jobs = await page.query_selector_all("[data-view-name='job-card']")
            print(f"✅ Found {len(jobs)} jobs using [data-view-name='job-card']")
        except:
            print("❌ Alternative selector failed, trying generic job card selector...")
            await page.wait_for_selector(".base-card", timeout=10000)
            jobs = await page.query_selector_all(".base-card")
            print(f"✅ Found {len(jobs)} jobs using .base-card")

    job_data = []
    
    # First, collect all job URLs to visit
    job_urls = []
    for job in jobs:
        try:
            # Try multiple selectors for job links
            link_element = await job.query_selector(".base-search-card__title a")
            if not link_element:
                link_element = await job.query_selector("h3 a")
            if not link_element:
                link_element = await job.query_selector("a")
            
            if link_element:
                job_url = await link_element.get_attribute("href")
                if job_url:
                    # Clean up the URL to get proper job link
                    if "linkedin.com/jobs/view/" in job_url:
                        job_urls.append(job_url)
                    elif "currentJobId=" in job_url:
                        # Extract job ID and create direct link
                        import re
                        job_id_match = re.search(r'currentJobId=(\d+)', job_url)
                        if job_id_match:
                            job_id = job_id_match.group(1)
                            direct_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                            job_urls.append(direct_url)
                    else:
                        job_urls.append(job_url)
                        
        except Exception as e:
            print(f"Error collecting job URL: {e}")
            continue
    
    print(f"📝 Found {len(job_urls)} job URLs to process...")
    
    # Now visit each job URL to get details and apply links
    successful_jobs = 0
    for i, job_url in enumerate(job_urls):
        if successful_jobs >= 10:  # Limit to 10 jobs to avoid detection
            print(f"\n🛑 Limiting to 10 jobs to avoid LinkedIn detection")
            break
            
        try:
            print(f"\n🔍 Processing job {i+1}/{len(job_urls)}...")
            
            # Add random delay between requests
            import random
            delay = random.uniform(3, 7)
            await page.wait_for_timeout(int(delay * 1000))
            
            # Navigate to the individual job page
            await page.goto(job_url, timeout=30000)
            await page.wait_for_timeout(3000)  # Wait longer for page to load completely
            
            # Check if we got redirected to legal/agreement page
            current_job_url = page.url
            if "user-agreement" in current_job_url or "legal" in current_job_url:
                print(f"   ⚠️ Job page redirected to legal page, skipping...")
                continue
            
            # Extract job details from the individual job page
            title = ""
            company = ""
            location = ""
            posted = ""
            apply_link = ""
            
            try:
                # Extract title
                title_element = await page.query_selector("h1")
                if title_element:
                    title = await title_element.inner_text()
                    title = title.strip()
            except:
                pass
            
            try:
                # Extract company
                company_element = await page.query_selector(".job-details-jobs-unified-top-card__company-name a")
                if not company_element:
                    company_element = await page.query_selector(".job-details-jobs-unified-top-card__company-name")
                if company_element:
                    company = await company_element.inner_text()
                    company = company.strip()
            except:
                pass
            
            try:
                # Extract location - try multiple selectors for job detail pages
                location_element = await page.query_selector(".job-details-jobs-unified-top-card__bullet")
                if not location_element:
                    location_element = await page.query_selector(".job-details-jobs-unified-top-card__primary-description")
                if not location_element:
                    location_element = await page.query_selector("[data-test-id='job-details-job-summary__location']")
                if not location_element:
                    location_element = await page.query_selector(".jobs-unified-top-card__bullet")
                
                if location_element:
                    location_text = await location_element.inner_text()
                    # Clean up location text (take only the first line that looks like a location)
                    lines = location_text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if any(keyword in line.lower() for keyword in ['india', 'remote', 'on-site', 'hybrid', 'bengaluru', 'mumbai', 'delhi', 'hyderabad', 'pune', 'chennai', 'gurugram']):
                            location = line
                            break
                    if not location:
                        location = lines[0].strip() if lines else ""
                else:
                    # Fallback: look for location patterns in page text
                    page_text = await page.inner_text("body")
                    import re
                    location_patterns = [
                        r'([\w\s]+,\s*[\w\s]+,\s*India\s*\([^)]+\))',
                        r'([\w\s]+,\s*[\w\s]+,\s*India)',
                        r'(\w+,\s*\w+\s*\([^)]+\))',
                    ]
                    for pattern in location_patterns:
                        match = re.search(pattern, page_text)
                        if match:
                            location = match.group(1).strip()
                            break
            except:
                pass
            
            try:
                # Extract posted time - try multiple selectors for job detail pages
                posted_element = await page.query_selector(".job-details-jobs-unified-top-card__content-container time")
                if not posted_element:
                    posted_element = await page.query_selector("time")
                if not posted_element:
                    posted_element = await page.query_selector("[data-test-id='job-details-job-summary__posted-time']")
                if not posted_element:
                    posted_element = await page.query_selector(".jobs-unified-top-card__subtitle-secondary-grouping time")
                
                if posted_element:
                    posted_text = await posted_element.inner_text()
                    posted = posted_text.strip()
                else:
                    # Fallback: look for time patterns in page text
                    page_text = await page.inner_text("body")
                    import re
                    time_patterns = [
                        r'(\d+\s+(?:minute|hour|day)s?\s+ago)',
                        r'(Posted\s+\d+\s+(?:minute|hour|day)s?\s+ago)',
                        r'(\d+[mhd]\s+ago)',
                    ]
                    for pattern in time_patterns:
                        match = re.search(pattern, page_text, re.IGNORECASE)
                        if match:
                            posted = match.group(1).strip()
                            break
            except:
                pass
            
            # Extract apply link - this is the key part!
            try:
                # Wait a bit more for the page to fully load
                await page.wait_for_timeout(3000)
                
                # Look for the actual Apply button with more comprehensive selectors
                apply_button = None
                apply_link = ""
                
                # Try different apply button selectors in order of preference
                apply_selectors = [
                    # The specific apply button you showed
                    "button.jobs-apply-button",
                    "#jobs-apply-button-id",
                    "button[aria-label*='Apply to'][aria-label*='on company website']",
                    
                    # External apply links
                    "a[data-tracking-control-name='public_jobs_apply-link-offsite']",
                    "a[data-tracking-control-name='public_jobs_apply-link-external']", 
                    ".jobs-apply-button a[href]",
                    "a[href*='apply'][href*='http']",  # External apply links
                    
                    # Easy Apply buttons
                    "button[aria-label*='Easy Apply']",
                    "button[data-control-name*='easy_apply']",
                ]
                
                print(f"   🔍 Looking for apply button...")
                
                for i, selector in enumerate(apply_selectors):
                    try:
                        apply_button = await page.query_selector(selector)
                        if apply_button:
                            print(f"   ✅ Found apply element with selector {i+1}: {selector}")
                            break
                    except:
                        continue
                
                if apply_button:
                    # Check if it's a link (external apply) or button (Easy Apply)
                    tag_name = await apply_button.evaluate("el => el.tagName.toLowerCase()")
                    
                    if tag_name == "a":
                        # It's a link - get the href
                        apply_href = await apply_button.get_attribute("href")
                        if apply_href and not ("user-agreement" in apply_href or "legal" in apply_href):
                            apply_link = apply_href
                            print(f"   ✅ Found external apply link: {apply_link[:80]}...")
                        else:
                            apply_link = "External apply link (legal redirect detected)"
                            print(f"   ⚠️ Apply link redirects to legal page")
                    
                    elif tag_name == "button":
                        # It's a button - check if it has onclick or if it's Easy Apply
                        button_text = await apply_button.inner_text()
                        button_aria = await apply_button.get_attribute("aria-label")
                        
                        if "Easy Apply" in (button_text + " " + (button_aria or "")):
                            apply_link = job_url  # Use the LinkedIn job URL for Easy Apply
                            print(f"   ✅ Found Easy Apply button - using LinkedIn URL")
                        else:
                            # For external apply buttons (like the jobs-apply-button), try to click them
                            print(f"   🔗 Found external apply button, attempting to get URL...")
                            try:
                                # Get current state
                                current_pages = len(context.pages)
                                current_url = page.url
                                
                                # Try scrolling first
                                await apply_button.scroll_into_view_if_needed()
                                await page.wait_for_timeout(1000)
                                
                                # Use JavaScript click directly
                                print(f"   🔧 Using JavaScript click...")
                                await apply_button.evaluate("el => el.click()")
                                
                                # Wait for potential redirect or new tab
                                await page.wait_for_timeout(3000)
                                
                                # Check for new tab
                                new_pages = len(context.pages)
                                if new_pages > current_pages:
                                    new_page = context.pages[-1]
                                    try:
                                        await new_page.wait_for_load_state('domcontentloaded', timeout=8000)
                                        apply_link = new_page.url
                                        print(f"   ✅ Found external apply URL in new tab: {apply_link[:80]}...")
                                        await new_page.close()
                                    except:
                                        apply_link = new_page.url
                                        print(f"   ✅ Got new tab URL: {apply_link[:80]}...")
                                        await new_page.close()
                                else:
                                    # Check for redirect in current page
                                    new_url = page.url
                                    if new_url != current_url and new_url != job_url:
                                        apply_link = new_url
                                        print(f"   ✅ Page redirected to: {apply_link[:80]}...")
                                        # Go back to job page
                                        await page.goto(job_url, timeout=15000)
                                        await page.wait_for_timeout(1000)
                                    else:
                                        # Button clicked but no navigation - might be a different type
                                        button_aria = await apply_button.get_attribute("aria-label")
                                        if button_aria and "company website" in button_aria.lower():
                                            apply_link = "External company website application"
                                        else:
                                            apply_link = "External application (click successful)"
                                        print(f"   ✅ Apply button clicked successfully")
                                        
                            except Exception as e:
                                apply_link = "External apply available (interaction error)"
                                print(f"   ⚠️  Error with apply button: {str(e)[:40]}...")
                    
                else:
                    # If no apply button found, try to look for any apply-related text
                    page_content = await page.content()
                    if "Easy Apply" in page_content:
                        apply_link = "Easy Apply (LinkedIn - button not detected)"
                        print(f"   ⚠️  Easy Apply text found but button not detected")
                    elif "Apply" in page_content:
                        apply_link = "Apply option available (button not detected)"
                        print(f"   ⚠️  Apply text found but button not detected")
                    else:
                        apply_link = "No apply option found"
                        print(f"   ❌ No apply button or text found")
                
            except Exception as e:
                print(f"   ⚠️  Error getting apply link: {e}")
                apply_link = "Error getting apply link"

            if title:  # Only add jobs with titles
                job_data.append([title, company, location, posted, apply_link])
                print(f"   ✅ {title} | {company} | {location} | {posted} | Apply: {apply_link[:50] if len(apply_link) > 50 else apply_link}")
                successful_jobs += 1
            else:
                print("   ❌ Skipped - no title found")
                
        except Exception as e:
            print(f"   ⚠️  Error processing job: {e}")
            continue

    if job_data:
        print(f"\n✅ Found {len(job_data)} jobs, saving to Google Sheets...")
        
        # Clear all existing data in the sheet
        try:
            SHEET.clear()
            print("🗑️ Cleared previous data from Google Sheets")
        except Exception as e:
            print(f"⚠️ Warning: Could not clear sheet: {e}")
        
        # Add headers
        SHEET.insert_row(['Title', 'Company', 'Location', 'Posted', 'Apply Link'], 1)
        
        # Add all job data
        SHEET.append_rows(job_data)
        print("✅ Data saved successfully!")
    else:
        print("❌ No jobs found to save.")

    # Clean up temporary file
    try:
        os.remove('linkedin_state.json')
    except:
        pass

    await browser.close()

async def main():
    async with async_playwright() as playwright:
        # Scrape jobs
        await scrape_jobs(playwright)

if __name__ == "__main__":
    asyncio.run(main())
