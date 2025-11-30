"""
Current Affairs Magazine Downloader
Downloads the latest VisionIAS monthly workbook PDF
Uses Selenium to handle JavaScript-rendered content (Livewire)
"""

import requests
from bs4 import BeautifulSoup
import os
import logging
from pathlib import Path
from datetime import datetime
import re
import time

logger = logging.getLogger(__name__)

# Try to import Playwright (preferred) or Selenium (fallback)
PLAYWRIGHT_AVAILABLE = False
SELENIUM_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
    logger.info("✅ Playwright available - will use for JavaScript rendering")
except ImportError:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        SELENIUM_AVAILABLE = True
        logger.info("✅ Selenium available - will use as fallback")
    except ImportError:
        logger.warning("⚠️ Neither Playwright nor Selenium available. Install with: pip install playwright (recommended) or pip install selenium")

def download_with_playwright(url, download_dir):
    """Use Playwright to find download button, click it, and capture the download"""
    logger.info("🌐 Using Playwright to find and click download button...")
    
    try:
        with sync_playwright() as p:
            # Launch browser (headless)
            browser = p.chromium.launch(headless=True)
            
            # Set up download path
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                accept_downloads=True
            )
            page = context.new_page()
            
            logger.info(f"⏳ Loading page: {url}")
            page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for dynamic content to load
            logger.info("⏳ Waiting for dynamic content to load...")
            page.wait_for_timeout(5000)  # Give Livewire time to load
            
            # Strategy 1: Look for download button/span with text "download" or "Download"
            logger.info("🔍 Looking for download button...")
            
            # Try multiple selectors for download buttons
            download_selectors = [
                "button:has-text('Download')",
                "a:has-text('Download')",
                "span:has-text('Download')",
                "button:has-text('download')",
                "a:has-text('download')",
                "span:has-text('download')",
                "[class*='download']",
                "[id*='download']",
                "button[download]",
                "a[download]"
            ]
            
            download_button = None
            for selector in download_selectors:
                try:
                    elements = page.query_selector_all(selector)
                    for elem in elements:
                        text = elem.inner_text().lower()
                        # Check if it's actually a download button (not just containing "download" in class)
                        if 'download' in text or elem.get_attribute('download'):
                            # Make sure it's visible and clickable
                            if elem.is_visible():
                                download_button = elem
                                logger.info(f"✅ Found download button: {selector} - Text: {elem.inner_text()[:50]}")
                                break
                    if download_button:
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            # Strategy 2: Look for buttons/links containing "workbook" and "download"
            if not download_button:
                logger.info("🔍 Looking for workbook download button...")
                all_buttons = page.query_selector_all("button, a, span")
                for btn in all_buttons:
                    try:
                        text = btn.inner_text().lower()
                        if ('download' in text and 'workbook' in text) or ('download' in text and 'monthly' in text):
                            if btn.is_visible():
                                download_button = btn
                                logger.info(f"✅ Found workbook download button: {text[:50]}")
                                break
                    except:
                        continue
            
            # Strategy 3: Look for any clickable element with download attribute
            if not download_button:
                logger.info("🔍 Looking for elements with download attribute...")
                download_elements = page.query_selector_all("[download]")
                for elem in download_elements:
                    if elem.is_visible():
                        download_button = elem
                        logger.info(f"✅ Found element with download attribute")
                        break
            
            if download_button:
                # Click the download button
                logger.info("🖱️ Clicking download button...")
                try:
                    # Use wait_for_download to wait for the download to start
                    with page.expect_download(timeout=10000) as download_info:
                        download_button.click(timeout=5000)
                    
                    download = download_info.value
                    download_filename = download.suggested_filename
                    download_path = os.path.join(download_dir, download_filename)
                    logger.info(f"📥 Download started: {download_filename}")
                    download.save_as(download_path)
                    
                    # Wait a bit to ensure file is saved
                    page.wait_for_timeout(1000)
                    
                    if os.path.exists(download_path):
                        logger.info(f"✅ Download completed: {download_path}")
                        browser.close()
                        return download_path
                    else:
                        logger.warning(f"⚠️ Download path doesn't exist: {download_path}")
                except Exception as e:
                    logger.error(f"❌ Error clicking download button: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Strategy 4: Try to find direct PDF links as fallback
            try:
                logger.info("🔍 Looking for direct PDF links...")
                pdf_links = page.query_selector_all("a[href$='.pdf']")
                if pdf_links:
                    pdf_link = pdf_links[0].get_attribute('href')
                    if not pdf_link.startswith('http'):
                        pdf_link = "https://visionias.in" + pdf_link if pdf_link.startswith("/") else "https://visionias.in/" + pdf_link
                    logger.info(f"📄 Found PDF link: {pdf_link}")
                    browser.close()
                    return pdf_link
            except Exception as e:
                logger.debug(f"Error finding PDF links: {e}")
            
            browser.close()
            
            if not download_path:
                logger.error("❌ No download button found and no PDF links found")
                logger.info("💡 Saving page HTML for debugging...")
                # Re-open page to get content if needed
                try:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto(url, wait_until='networkidle', timeout=30000)
                    page.wait_for_timeout(3000)
                    content = page.content()
                    browser.close()
                    debug_file = os.path.join(download_dir, "debug_rendered_page.html")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info(f"💾 Saved rendered page HTML to {debug_file}")
                except:
                    pass
            
            return download_path if download_path and os.path.exists(download_path) else None
            
    except Exception as e:
        logger.error(f"❌ Playwright error: {e}")
        import traceback
        traceback.print_exc()
        return None

def download_with_selenium(url, download_dir):
    """Use Selenium to render JavaScript and find PDF links (fallback)"""
    logger.info("🌐 Using Selenium to render JavaScript content...")
    
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)
        time.sleep(5)
        
        pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf')]")
        if pdf_links:
            pdf_link = pdf_links[0].get_attribute('href')
            logger.info(f"📄 Found PDF link via Selenium: {pdf_link}")
            return pdf_link
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                if not href.startswith("http"):
                    href = "https://visionias.in" + href if href.startswith("/") else "https://visionias.in/" + href
                return href
        
        return None
    except Exception as e:
        logger.error(f"❌ Selenium error: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def process_extracted_pdf(pdf_path: str, pinecone_handler=None, content_store=None):
    """
    Process an extracted PDF through the same pipeline as uploaded PDFs:
    1. Extract and clean text
    2. Chunk using hierarchical chunker
    3. Classify metadata with GPT-4o-mini (batch processing)
    4. Store in Pinecone (embeddings + metadata)
    5. Store in SQLite content store (full content)
    
    Args:
        pdf_path: Path to the extracted PDF file
        pinecone_handler: PineconeHandler instance (will create if None)
        content_store: ContentStore instance (will create if None)
        
    Returns:
        dict with processing summary (chunks_added, filename, status)
    """
    import sys
    from pathlib import Path
    
    # Handle imports - support both relative (when imported) and absolute (when run directly)
    try:
        from ..utils.hierarchical_chunker import HierarchicalChunker
        from ..utils.metadata_enricher import classify_chunks_batch
        from ..utils.pinecone_handler import PineconeHandler
        from ..utils.content_store import ContentStore
    except ImportError:
        # If relative imports fail, add backend to path and use absolute imports
        backend_path = Path(__file__).parent.parent.parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        from app.utils.hierarchical_chunker import HierarchicalChunker
        from app.utils.metadata_enricher import classify_chunks_batch
        from app.utils.pinecone_handler import PineconeHandler
        from app.utils.content_store import ContentStore
    
    from openai import OpenAI
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📚 Processing extracted PDF: {pdf_path}")
    logger.info(f"{'='*60}")
    
    try:
        # Initialize OpenAI client and chunker
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        chunker = HierarchicalChunker(llm_client=openai_client)
        
        # Get or create handlers
        if pinecone_handler is None:
            logger.info("🔧 Initializing PineconeHandler...")
            pinecone_handler = PineconeHandler()
        
        if content_store is None:
            logger.info("🔧 Initializing ContentStore...")
            content_store = ContentStore()
        
        # Get filename
        filename = os.path.basename(pdf_path)
        logger.info(f"📄 Filename: {filename}")
        
        # Step 1: Chunk PDF using hierarchical chunker (same as upload.py)
        logger.info("🔍 Chunking PDF...")
        chunks = chunker.process_pdf(pdf_path, filename)
        
        if not chunks:
            logger.warning(f"⚠️ No chunks created from {filename}")
            return {
                "filename": filename,
                "status": "failed",
                "reason": "No chunks created",
                "chunks_added": 0
            }
        
        logger.info(f"✅ Created {len(chunks)} chunks")
        
        # Step 2: Classify chunks with GPT-4o-mini (batch processing - same as upload.py)
        logger.info(f"\n🤖 Classifying {len(chunks)} chunks with GPT-4o-mini (batch processing)...")
        classified_chunks = classify_chunks_batch(chunks, openai_client)
        logger.info(f"✅ Classification complete for {len(classified_chunks)} chunks")
        
        # Show first 3 chunks with classification
        logger.info(f"\n📝 First 3 chunks with classification:")
        for i, chunk in enumerate(classified_chunks[:3], 1):
            meta = chunk.get('metadata', {})
            logger.info(f"\n   Chunk {i}:")
            logger.info(f"      • Content preview: {chunk['content'][:150].replace(chr(10), ' ')}...")
            logger.info(f"      • Word count: {len(chunk['content'].split())} words")
            logger.info(f"      • Major Domain: {meta.get('major_domain', 'N/A')}")
            logger.info(f"      • Sub Domain: {meta.get('sub_domain', 'N/A')}")
            logger.info(f"      • Micro Topic: {meta.get('micro_topic', 'N/A')}")
            if meta.get('sub_topics'):
                logger.info(f"      • Sub Topics: {', '.join(meta.get('sub_topics', []))}")
        
        # Step 3: Store classified chunks in Pinecone (generates embeddings automatically)
        logger.info(f"\n💾 Storing {len(classified_chunks)} chunks in Pinecone (generating embeddings)...")
        pinecone_handler.add_documents(classified_chunks)
        logger.info(f"✅ Successfully stored {len(classified_chunks)} chunks in Pinecone")
        
        # Step 4: Store in SQLite content store (full content with metadata)
        logger.info(f"\n💾 Storing {len(classified_chunks)} chunks in SQLite content store...")
        
        # Import match_and_store function
        try:
            from ..routes.upload_content_store import match_and_store_pinecone_chunks
        except ImportError:
            from app.routes.upload_content_store import match_and_store_pinecone_chunks
        
        # Match and store chunks
        matching_results = match_and_store_pinecone_chunks(
            content_chunks=classified_chunks,
            pinecone_handler=pinecone_handler,
            content_store=content_store,
            filename=filename
        )
        
        logger.info(f"✅ SQLite storage complete:")
        logger.info(f"   • Stored: {matching_results.get('stored_count', 0)} chunks")
        logger.info(f"   • Match rate: {matching_results.get('match_rate', 0):.1%}")
        
        logger.info(f"\n✅ Successfully processed {filename}")
        logger.info(f"   • Chunks added to Pinecone: {len(classified_chunks)}")
        logger.info(f"   • Chunks added to SQLite: {matching_results.get('stored_count', 0)}")
        logger.info(f"{'='*60}\n")
        
        return {
            "filename": filename,
            "status": "success",
            "chunks_added": len(classified_chunks),
            "pinecone_chunks": len(classified_chunks),
            "sqlite_chunks": matching_results.get('stored_count', 0),
            "match_rate": matching_results.get('match_rate', 0)
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing {pdf_path}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "filename": os.path.basename(pdf_path),
            "status": "failed",
            "reason": str(e),
            "chunks_added": 0
        }



def download_latest_visionias_workbook(download_dir="data/geography_current_affairs", extract_sections: bool = True):
    """
    Download the latest VisionIAS monthly current affairs workbook PDF.
    Optionally extracts only Geography and Environment sections.
    
    Args:
        download_dir: Directory to save the downloaded PDF
        extract_sections: If True, extract only Geography/Environment sections
        
    Returns:
        Path to the downloaded (and optionally extracted) PDF file
    """
    url = "https://visionias.in/current-affairs/downloads/monthly-current-affairs-workbook"
    
    # Create download directory
    os.makedirs(download_dir, exist_ok=True)
    logger.info(f"📁 Download directory: {download_dir}")
    
    # Set headers to mimic a browser (some sites block requests without user-agent)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        logger.info(f"🌐 Accessing VisionIAS page: {url}")
        response = requests.get(url, timeout=30, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        logger.info(f"✅ Page accessed successfully (status: {response.status_code})")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to access VisionIAS page: {e}")
        raise Exception(f"Failed to access VisionIAS page: {e}")
    
    # Parse HTML
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find PDF links - try multiple strategies
    pdf_link = None
    pdf_filename = None
    
    # Strategy 1: Look for direct PDF links in <a> tags
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            pdf_link = href
            # Try to get filename from link text or href
            if a.text.strip():
                pdf_filename = a.text.strip()
            else:
                pdf_filename = href.split("/")[-1]
            logger.info(f"📄 Found PDF link (strategy 1): {pdf_link}")
            break
    
    # Strategy 2: Look for PDF links in download buttons or specific classes
    if not pdf_link:
        # Look for common download button classes/ids
        download_selectors = [
            {"class": "download"},
            {"class": "btn-download"},
            {"id": "download"},
            {"class": "pdf-download"}
        ]
        
        for selector in download_selectors:
            elements = soup.find_all("a", selector)
            for elem in elements:
                href = elem.get("href", "")
                if href.lower().endswith(".pdf"):
                    pdf_link = href
                    pdf_filename = href.split("/")[-1]
                    logger.info(f"📄 Found PDF link (strategy 2): {pdf_link}")
                    break
            if pdf_link:
                break
    
    # Strategy 3: Look for any link containing "workbook" or "current affairs" and ending in .pdf
    if not pdf_link:
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.text.lower()
            if (".pdf" in href and 
                ("workbook" in href or "workbook" in text or 
                 "current" in href or "current" in text or
                 "monthly" in href or "monthly" in text)):
                pdf_link = a["href"]
                pdf_filename = href.split("/")[-1]
                logger.info(f"📄 Found PDF link (strategy 3): {pdf_link}")
                break
    
    # Strategy 4: If no PDF found, use Playwright (preferred) or Selenium (fallback) to click download button
    if not pdf_link:
        if PLAYWRIGHT_AVAILABLE:
            logger.info("🔄 No PDF found in static HTML, trying Playwright to find and click download button...")
            downloaded_file = download_with_playwright(url, download_dir)
            if downloaded_file:
                # If Playwright downloaded the file directly (returns file path), return it
                if isinstance(downloaded_file, str) and os.path.exists(downloaded_file):
                    logger.info(f"✅ File downloaded successfully via Playwright: {downloaded_file}")
                    return downloaded_file
                # Otherwise, it might have returned a URL
                elif isinstance(downloaded_file, str) and downloaded_file.startswith('http'):
                    pdf_link = downloaded_file
        elif SELENIUM_AVAILABLE:
            logger.info("🔄 No PDF found in static HTML, trying Selenium to render JavaScript...")
            pdf_link = download_with_selenium(url, download_dir)
        
        if pdf_link and isinstance(pdf_link, str) and pdf_link.startswith('http'):
            pdf_filename = pdf_link.split("/")[-1]
            if "?" in pdf_filename:
                pdf_filename = pdf_filename.split("?")[0]
    
    if not pdf_link and not (PLAYWRIGHT_AVAILABLE and downloaded_file and os.path.exists(downloaded_file)):
        logger.error("❌ No PDF link found on VisionIAS page")
        # Log page structure for debugging
        logger.debug(f"Page title: {soup.title.string if soup.title else 'No title'}")
        # Save HTML for debugging
        debug_file = os.path.join(download_dir, "debug_page.html")
        with open(debug_file, "w", encoding="utf-8") as f:
            f.write(response.text)
        logger.info(f"💾 Saved page HTML to {debug_file} for debugging")
        
        if not PLAYWRIGHT_AVAILABLE and not SELENIUM_AVAILABLE:
            logger.info("💡 Tip: Install Playwright to handle JavaScript-rendered content:")
            logger.info("   pip install playwright")
            logger.info("   playwright install chromium")
            logger.info("   Or install Selenium: pip install selenium")
        
        raise Exception("No PDF link found on VisionIAS page. The page may use JavaScript to load content. Check debug_page.html for page structure.")
    
    # Handle relative URLs
    if not pdf_link.startswith("http"):
        if pdf_link.startswith("/"):
            pdf_link = "https://visionias.in" + pdf_link
        else:
            pdf_link = "https://visionias.in/" + pdf_link
    
    # Extract filename if not already extracted
    if not pdf_filename:
        pdf_filename = pdf_link.split("/")[-1]
        # Clean filename (remove query parameters if any)
        if "?" in pdf_filename:
            pdf_filename = pdf_filename.split("?")[0]
    
    # Ensure filename has .pdf extension
    if not pdf_filename.lower().endswith(".pdf"):
        pdf_filename += ".pdf"
    
    save_path = os.path.join(download_dir, pdf_filename)
    
    # Check if file already exists
    if os.path.exists(save_path):
        logger.info(f"⚠️ File already exists: {save_path}")
        logger.info(f"   Skipping download. Delete file if you want to re-download.")
        # Continue to extraction step if requested (don't return early)
        if not extract_sections:
            return save_path
    
    # Download file
    logger.info(f"📥 Downloading: {pdf_filename}")
    logger.info(f"   From: {pdf_link}")
    
    try:
        with requests.get(pdf_link, stream=True, headers=headers, timeout=60) as r:
            r.raise_for_status()
            
            # Check if it's actually a PDF (check content-type)
            content_type = r.headers.get('content-type', '').lower()
            if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
                logger.warning(f"⚠️ Content-Type is '{content_type}', might not be a PDF")
            
            # Get file size if available
            file_size = r.headers.get('content-length')
            if file_size:
                file_size_mb = int(file_size) / (1024 * 1024)
                logger.info(f"   File size: {file_size_mb:.2f} MB")
            
            # Download with progress
            total_size = 0
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        total_size += len(chunk)
            
            # Verify file was downloaded (check if it's actually a PDF)
            if total_size == 0:
                os.remove(save_path)
                raise Exception("Downloaded file is empty")
            
            # Check if file starts with PDF magic bytes
            with open(save_path, "rb") as f:
                first_bytes = f.read(4)
                if first_bytes != b'%PDF':
                    logger.warning(f"⚠️ File doesn't appear to be a valid PDF (first bytes: {first_bytes})")
                    # Don't delete, might still be valid
            
            logger.info(f"✅ Successfully downloaded: {save_path}")
            logger.info(f"   File size: {total_size / (1024 * 1024):.2f} MB")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to download PDF: {e}")
        # Clean up partial download
        if os.path.exists(save_path):
            os.remove(save_path)
        raise Exception(f"Failed to download PDF: {e}")
    
    # Step 2: Extract Geography and Environment sections if requested
    if extract_sections:
        try:
            from .pdf_section_extractor import extract_sections_with_validation
            
            logger.info("\n" + "="*60)
            logger.info("📚 Extracting Geography and Environment sections...")
            logger.info("="*60)
            
            extracted_file = extract_sections_with_validation(
                save_path,
                keywords=['geography', 'environment']
            )
            
            if extracted_file:
                logger.info(f"✅ Extracted sections saved to: {extracted_file}")
                # Return the extracted file instead of the full PDF
                return extracted_file
            else:
                logger.warning("⚠️ Could not extract sections, returning full PDF")
                return save_path
        except ImportError:
            logger.warning("⚠️ PyMuPDF not available for section extraction. Install with: pip install pymupdf")
            logger.info("   Returning full PDF instead")
            return save_path
        except Exception as e:
            logger.error(f"❌ Error extracting sections: {e}")
            logger.info("   Returning full PDF instead")
            return save_path
    
    return save_path


if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Step 1: Download the full magazine and extract sections
        logger.info("="*60)
        logger.info("🚀 Starting Current Affairs Downloader")
        logger.info("="*60)
        latest_file = download_latest_visionias_workbook(extract_sections=True)
        
        # Verify we got the extracted PDF, not the full one
        if "_geo_env" not in latest_file:
            logger.warning(f"\n⚠️ Warning: Expected extracted PDF but got: {latest_file}")
            logger.info(f"   This might be the full PDF. Checking for extracted version...")
            # Look for extracted version
            base_name = os.path.splitext(latest_file)[0]
            extracted_path = f"{base_name}_geo_env.pdf"
            if os.path.exists(extracted_path):
                latest_file = extracted_path
                logger.info(f"   ✅ Found extracted PDF: {latest_file}")
            else:
                logger.warning(f"   ⚠️ Extracted PDF not found. Processing full PDF instead.")
        
        logger.info(f"\n✅ Latest workbook downloaded and extracted: {latest_file}")
        
        # Step 2: Initialize handlers for new storage system
        logger.info(f"\n{'='*60}")
        logger.info(f"🔧 Initializing storage handlers...")
        logger.info(f"{'='*60}")
        
        # Import handlers
        import sys
        from pathlib import Path
        backend_path = Path(__file__).parent.parent.parent
        if str(backend_path) not in sys.path:
            sys.path.insert(0, str(backend_path))
        
        from app.utils.pinecone_handler import PineconeHandler
        from app.utils.content_store import ContentStore
        
        # Initialize Pinecone handler
        logger.info("🔧 Initializing PineconeHandler...")
        pinecone_handler = PineconeHandler()
        logger.info("✅ PineconeHandler initialized")
        
        # Initialize content store
        logger.info("🔧 Initializing ContentStore...")
        content_store = ContentStore()
        logger.info("✅ ContentStore initialized")
        
        # Step 3: Process the extracted PDF through chunking and classification pipeline
        logger.info(f"\n📚 Processing extracted PDF through chunking pipeline...")
        result = process_extracted_pdf(
            latest_file,
            pinecone_handler=pinecone_handler,
            content_store=content_store
        )
        
        # Step 4: Display results
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 FINAL RESULTS")
        logger.info(f"{'='*60}")
        
        if result["status"] == "success":
            logger.info(f"✅ Successfully processed {result['filename']}")
            logger.info(f"   • Chunks added to Pinecone: {result.get('pinecone_chunks', 0)}")
            logger.info(f"   • Chunks added to SQLite: {result.get('sqlite_chunks', 0)}")
            logger.info(f"   • Match rate: {result.get('match_rate', 0):.1%}")
            logger.info(f"\n🎉 Current affairs processing complete!")
        else:
            logger.error(f"❌ Failed to process {result['filename']}")
            logger.error(f"   • Reason: {result.get('reason', 'Unknown error')}")
            exit(1)
            
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


