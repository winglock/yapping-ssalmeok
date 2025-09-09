import os
import json
import time
import random
import sys
import re
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
import google.generativeai as genai
import google.api_core.exceptions
from urllib.parse import quote

# Load environment variables
load_dotenv()

class TwitterBot:
    def __init__(self):
        self.username = os.getenv('TWITTER_USERNAME')
        self.password = os.getenv('TWITTER_PASSWORD')
        self.cookies_file = os.getenv('COOKIES_FILE')
        self.community_url = os.getenv('COMMUNITY_URL')
        # Set Chrome profile path to a custom directory
        self.chrome_profile = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_profile')
        
        # Processed tweets file for persistence
        self.processed_tweets_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'processed_tweets.json')
        
        # Bot stop flag
        self.bot_should_stop = False
        
        # Search-related variables
        self.current_keyword = None
        self.search_mode = False
        
        # Required keywords that must be included in responses
        self.required_keywords = []
        
        # --- [MODIFIED] API Key Rotation Setup ---
        gemini_api_keys_str = os.getenv('GEMINI_API_KEY')
        if not gemini_api_keys_str:
            raise ValueError("GEMINI_API_KEY not found in environment variables. Please provide one or more keys separated by commas.")
        
        self.gemini_api_keys = [key.strip() for key in gemini_api_keys_str.split(',') if key.strip()]
        if not self.gemini_api_keys:
            raise ValueError("No valid GEMINI_API_KEY found after parsing. Please check your .env file.")
            
        self.current_api_key_index = 0
        self.configure_gemini()
        print(f"✅ Loaded {len(self.gemini_api_keys)} Gemini API Key(s). Starting with key #1.")
        # --- [END MODIFIED] ---
        
        # Load GEMINI system prompt from .env
        self.system_prompt = os.getenv('GEMINI_SYSTEM_PROMPT', '').strip()
        if not self.system_prompt:
            raise ValueError("GEMINI_SYSTEM_PROMPT is missing in .env")
        
        # --- [MODIFIED] Dynamic typing speed variables - 1500-2000 CPM (0.03-0.04s) ---
        self.current_typing_speed = random.uniform(0.03, 0.04)
        self.typing_rhythm_changes = 2
        
        print("AI model and system prompt initialized successfully!")
        print("⚡ Typing speed: 1500-2000 CPM (Expert speed with enhanced humanization)")
        
        self.setup_driver()

    # --- [NEW] Method to configure Gemini with the current key ---
    def configure_gemini(self):
        """Configures the Gemini AI with the current API key."""
        try:
            current_key = self.gemini_api_keys[self.current_api_key_index]
            genai.configure(api_key=current_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash') # Use the latest efficient model
            print(f"🔄 Gemini AI configured with API Key #{self.current_api_key_index + 1}")
        except Exception as e:
            print(f"🚨 Failed to configure Gemini with API Key #{self.current_api_key_index + 1}: {e}")
            self.bot_should_stop = True

    # --- [NEW] Method to switch to the next API key ---
    def switch_to_next_api_key(self):
        """Switches to the next available Gemini API key."""
        print(f"🚨 Critical API error with Key #{self.current_api_key_index + 1}.")
        
        if len(self.gemini_api_keys) <= 1:
            print("🛑 Only one API key is available. Cannot switch. Stopping bot.")
            self.bot_should_stop = True
            return False

        self.current_api_key_index = (self.current_api_key_index + 1) % len(self.gemini_api_keys)
        print(f"⏳ Switching to next API Key (#{self.current_api_key_index + 1}/{len(self.gemini_api_keys)})...")
        self.configure_gemini()
        time.sleep(1) # Brief pause after switching
        return True

    def detect_language(self, text):
        """Detect if text is primarily English or Korean"""
        if not text:
            return 'korean'
        clean_text = re.sub(r'http\S+|www\S+|@\w+|#\w+', '', text)
        clean_text = re.sub(r'[^\w\s]', '', clean_text)
        korean_chars = len(re.findall(r'[가-힣]', clean_text))
        english_chars = len(re.findall(r'[a-zA-Z]', clean_text))
        total_chars = korean_chars + english_chars
        if total_chars == 0:
            return 'korean'
        if korean_chars / total_chars > 0.3:
            return 'korean'
        elif english_chars / total_chars > 0.7:
            return 'english'
        else:
            return 'korean' if korean_chars >= english_chars else 'english'

    def setup_driver(self):
        """Initialize the Chrome WebDriver with appropriate options"""
        try:
            os.makedirs(self.chrome_profile, exist_ok=True)
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument(f'--user-data-dir={self.chrome_profile}')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, 20)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("Opening Twitter...")
            self.driver.get("https://twitter.com")
            print("Twitter opened successfully!")
        except Exception as e:
            print(f"Error setting up Chrome driver: {str(e)}")
            if hasattr(self, 'driver'):
                self.driver.quit()
            raise e

    def clear_login_data(self):
        """Clear stored cookies and login data for fresh start"""
        try:
            if os.path.exists(self.cookies_file):
                os.remove(self.cookies_file)
                print("✅ Cleared stored cookies")
            self.driver.delete_all_cookies()
            print("✅ Cleared browser cookies")
            try:
                self.driver.execute_script("window.localStorage.clear();")
                self.driver.execute_script("window.sessionStorage.clear();")
                print("✅ Cleared browser storage")
            except:
                pass
            return True
        except Exception as e:
            print(f"Error clearing login data: {e}")
            return False

    def random_delay(self, min_seconds=0.05, max_seconds=0.15):
        """Add random delay to simulate human behavior"""
        time.sleep(random.uniform(min_seconds, max_seconds))

    # --- [MODIFIED] Typing speed update for 1500-2000 CPM ---
    def update_typing_speed(self):
        """Dynamically update typing speed to simulate natural variation - 1500-2000 CPM"""
        if self.typing_rhythm_changes % random.randint(5, 10) == 0:
            speed_change = random.uniform(-0.002, 0.002)
            self.current_typing_speed = max(0.03, min(0.04, self.current_typing_speed + speed_change))
        self.typing_rhythm_changes += 1

    # --- [MODIFIED] Dynamic delays adjusted for faster typing ---
    def get_dynamic_typing_delay(self, char_type='normal'):
        """Get typing delay based on character type and current rhythm"""
        self.update_typing_speed()
        base_delay = self.current_typing_speed
        if char_type == 'space':
            return base_delay + random.uniform(0.03, 0.06)
        elif char_type == 'punctuation':
            return base_delay + random.uniform(0.05, 0.12)
        elif char_type == 'newline':
            return base_delay + random.uniform(0.1, 0.18)
        else:
            return base_delay + random.uniform(-0.005, 0.005)

    def simulate_mouse_movement(self, element):
        """Simulate natural mouse movement to element"""
        try:
            actions = ActionChains(self.driver)
            x_offset = random.randint(-5, 5)
            y_offset = random.randint(-5, 5)
            actions.move_to_element_with_offset(element, x_offset, y_offset)
            actions.perform()
            self.random_delay(0.1, 0.3)
        except Exception as e:
            print(f"Error simulating mouse movement: {str(e)}")

    # --- [MODIFIED] Human-like typing with faster speed and enhanced humanization ---
    def type_like_human(self, element, text):
        """Type text like a human with natural variations and fast speed (1500-2000 CPM)"""
        try:
            element.clear()
            self.random_delay(0.2, 0.5)
            self.current_typing_speed = random.uniform(0.03, 0.04) # Set initial speed for this text
            self.typing_rhythm_changes = 0
            for i, char in enumerate(text):
                # Increased typo chance for more human-like fast typing
                if random.random() < 0.035 and i > 0:
                    wrong_char = random.choice('qwertyuiopasdfghjklzxcvbnm')
                    element.send_keys(wrong_char)
                    time.sleep(self.get_dynamic_typing_delay())
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(self.get_dynamic_typing_delay())
                
                element.send_keys(char)
                
                if char == ' ':
                    delay = self.get_dynamic_typing_delay('space')
                elif char in '.,!?':
                    delay = self.get_dynamic_typing_delay('punctuation')
                elif char in '\n':
                    delay = self.get_dynamic_typing_delay('newline')
                else:
                    delay = self.get_dynamic_typing_delay('normal')
                time.sleep(delay)

                # Increased "thinking pause" chance
                if random.random() < 0.025:
                    time.sleep(random.uniform(0.2, 0.5))
            self.random_delay(0.2, 0.4)
        except Exception as e:
            print(f"Error in human-like typing: {str(e)}")
            element.clear()
            element.send_keys(text)

    def human_like_click(self, element):
        """Click element in a human-like way"""
        try:
            self.simulate_mouse_movement(element)
            self.random_delay(0.1, 0.3)
            try:
                element.click()
            except:
                self.driver.execute_script("arguments[0].click();", element)
            self.random_delay(0.2, 0.5)
            return True
        except Exception as e:
            print(f"Error in human-like click: {str(e)}")
            return False

    def simulate_reading_behavior(self, tweet_element):
        """Simulate reading the tweet before replying - HYPER SPEED version"""
        try:
            tweet_text = self.get_tweet_text(tweet_element)
            if tweet_text:
                words = len(tweet_text.split())
                reading_time = (words / 350) * 60
                reading_time = max(0.2, min(reading_time, 1.0))
                time.sleep(random.uniform(reading_time * 0.8, reading_time * 1.2))
        except Exception:
            time.sleep(random.uniform(0.3, 0.7))

    def save_processed_tweets(self, processed_tweets):
        """Save processed tweets to file for persistence"""
        try:
            with open(self.processed_tweets_file, 'w') as f:
                json.dump(list(processed_tweets), f)
        except Exception as e:
            print(f"Error saving processed tweets: {str(e)}")

    def load_processed_tweets(self):
        """Load processed tweets from file"""
        try:
            with open(self.processed_tweets_file, 'r') as f:
                return set(json.load(f))
        except FileNotFoundError:
            return set()
        except Exception as e:
            print(f"Error loading processed tweets: {str(e)}")
            return set()

    def save_cookies(self):
        """Save cookies to file"""
        with open(self.cookies_file, 'w') as f:
            json.dump(self.driver.get_cookies(), f)

    def load_cookies(self):
        """Load cookies from file if exists"""
        try:
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
                for cookie in cookies:
                    if 'domain' in cookie and '.twitter.com' in cookie['domain']:
                        self.driver.add_cookie(cookie)
            return True
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f"Error loading cookies: {e}")
            return False

    def search_by_keyword(self, keyword):
        """Search for tweets with specific keyword"""
        try:
            encoded_keyword = quote(keyword)
            search_url = f"https://x.com/search?q={encoded_keyword}&src=typed_query&f=live"
            print(f"Searching for keyword: '{keyword}' at {search_url}")
            self.driver.get(search_url)
            time.sleep(5)
            if "search" in self.driver.current_url.lower():
                print(f"✅ Successfully navigated to search results for: '{keyword}'")
                return True
            else:
                print(f"❌ Failed to navigate to search page. Current URL: {self.driver.current_url}")
                return False
        except Exception as e:
            print(f"❌ Error searching for keyword '{keyword}': {str(e)}")
            return False

    def contains_keyword(self, tweet_text, keyword):
        """Check if tweet contains the specified keyword (case insensitive)"""
        return keyword.lower() in tweet_text.lower() if tweet_text and keyword else False

    def ensure_keywords_included(self, text, language):
        """Ensure all required keywords are included in the response"""
        if not self.required_keywords:
            return text
        missing_keywords = [kw for kw in self.required_keywords if kw.lower() not in text.lower()]
        if missing_keywords:
            print(f"⚠️ Missing keywords detected: {missing_keywords}")
            if language == 'english':
                text += f" Also, talking about {', '.join(missing_keywords)}."
            else:
                text += f" {' '.join(missing_keywords)}"
            print(f"✅ Added missing keywords.")
        return text

    def login(self):
        """Login to Twitter using various methods."""
        print("🚀 Starting login sequence...")
        try:
            self.driver.get("https://x.com/home")
            time.sleep(5)
            if "login" not in self.driver.current_url.lower() and "flow" not in self.driver.current_url.lower():
                print("✅ Already logged in via Chrome profile session!")
                if self.search_mode and self.current_keyword: return self.search_by_keyword(self.current_keyword)
                elif self.community_url: self.driver.get(self.community_url); time.sleep(3)
                return True
        except Exception as e:
            print(f"Error during session check: {e}. Proceeding with login attempts.")

        try:
            self.driver.get("https://x.com")
            time.sleep(2)
            if self.load_cookies():
                print("🍪 Cookies loaded from file. Refreshing page...")
                self.driver.refresh()
                time.sleep(5)
                if "login" not in self.driver.current_url.lower() and "flow" not in self.driver.current_url.lower():
                    print("✅ Successfully logged in with saved cookies!")
                    if self.search_mode and self.current_keyword: return self.search_by_keyword(self.current_keyword)
                    elif self.community_url: self.driver.get(self.community_url); time.sleep(3)
                    return True
            print("🍪 Login with saved cookies failed or no cookies found.")
        except Exception as e:
            print(f"Login with saved cookies failed: {e}. Proceeding to manual login.")

        try:
            self.driver.get('https://x.com/i/flow/login')
            time.sleep(5)
            username_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[autocomplete="username"]')))
            self.type_like_human(username_input, self.username)
            self.human_like_click(self.wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Next')]"))))
            print("Username entered.")
            time.sleep(3)
            try:
                password_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]')))
                self.type_like_human(password_input, self.password)
                self.human_like_click(self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[data-testid="LoginForm_Login_Button"]'))))
                print("Password entered.")
                time.sleep(7)
            except TimeoutException:
                print("⚠️ Password field not found. Trying verification step...")
                verification_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-testid="ocfEnterTextTextInput"]')))
                self.type_like_human(verification_input, self.username)
                verification_input.send_keys(Keys.RETURN)
                time.sleep(3)
                password_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="password"]')))
                self.type_like_human(password_input, self.password)
                self.human_like_click(self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[data-testid="LoginForm_Login_Button"]'))))
                print("Password entered after verification.")
                time.sleep(7)

            if "login" in self.driver.current_url.lower() or "flow" in self.driver.current_url.lower():
                print("❌ Manual login failed.")
                self.driver.save_screenshot("manual_login_failed.png")
                return False

            print("✅ Manual login successful!")
            self.save_cookies()
            print("🍪 New session cookies saved.")
            if self.search_mode and self.current_keyword: return self.search_by_keyword(self.current_keyword)
            elif self.community_url: self.driver.get(self.community_url)
            else: self.driver.get('https://x.com/home')
            time.sleep(5)
            return True
        except Exception as e:
            print(f"❌ An unexpected error occurred during manual login: {e}")
            self.driver.save_screenshot("manual_login_error.png")
            return False

    def get_tweet_text(self, tweet_element):
        """Extract text content from a tweet"""
        try:
            return tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="tweetText"]').text
        except: return None

    def get_tweet_id(self, tweet_element):
        """Extract unique identifier for a tweet, handling stale elements."""
        try:
            for _ in range(3):
                try:
                    time_element = tweet_element.find_element(By.CSS_SELECTOR, 'time')
                    return time_element.find_element(By.XPATH, '..').get_attribute('href')
                except StaleElementReferenceException:
                    time.sleep(0.5)
                    continue
            return None
        except: return None

    def is_own_tweet(self, tweet_element):
        """Check if the tweet is from our own account"""
        try:
            username_text = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="User-Name"]').text.lower()
            return os.getenv('TWITTER_USERNAME', '').lower() in username_text
        except: return True

    def is_reply_tweet(self, tweet_element):
        """Check if the tweet is a reply"""
        try:
            return len(tweet_element.find_elements(By.CSS_SELECTOR, '[data-testid="socialContext"]')) > 0
        except: return True

    def clean_text(self, text):
        """Clean text to ensure it only contains supported characters"""
        if not text: return "..."
        cleaned = ''.join(char for char in text if ord(char) < 128 or 0xAC00 <= ord(char) <= 0xD7A3)
        return cleaned.strip() or "..."

    def _generate_with_retry(self, prompt):
        """Internal helper to generate content with API key rotation."""
        initial_key_index = self.current_api_key_index
        for _ in range(len(self.gemini_api_keys)):
            if self.bot_should_stop: return None
            try:
                response = self.model.generate_content(prompt)
                return response.text.strip().strip('"')
            except Exception as e:
                error_str = str(e).lower()
                is_critical = any(k in error_str for k in ['quota', 'billing', '429', 'api key', 'permission denied'])
                if is_critical:
                    if not self.switch_to_next_api_key(): return None
                    if self.current_api_key_index == initial_key_index:
                        self.bot_should_stop = True
                        return None
                else:
                    print(f"❌ Non-critical API error: {e}")
                    return None
        self.bot_should_stop = True
        return None

    def generate_ai_response(self, tweet_text):
        """Generate a contextual response."""
        detected_language = self.detect_language(tweet_text)
        keywords_text = f"\n\nIMPORTANT: You must naturally include these keywords: {', '.join(self.required_keywords)}" if self.required_keywords else ""
        prompt = f"{self.system_prompt}\n\n트윗 내용: \"{tweet_text}\"{keywords_text}\n\n너의 한국어 답변:"
        if detected_language == 'english':
            prompt = f"""You are a friendly 20-something Korean guy commenting on Twitter. Respond in casual English to this tweet. Tweet: "{tweet_text}"{keywords_text}\n\nYour English reply:"""
        
        ai_reply = self._generate_with_retry(prompt)
        if ai_reply:
            ai_reply = self.clean_text(ai_reply) if detected_language == 'korean' else ai_reply.strip()
            ai_reply = self.ensure_keywords_included(ai_reply, detected_language)
            print(f"Generated AI response ({detected_language}, {len(ai_reply)} chars): {ai_reply}")
            return ai_reply
        return None

    def generate_quote_text(self, tweet_text):
        """Generate quote tweet text."""
        detected_language = self.detect_language(tweet_text)
        keywords_text = f"\n\nIMPORTANT: You must naturally include these keywords: {', '.join(self.required_keywords)}" if self.required_keywords else ""
        quote_prompt_base = os.getenv('GEMINI_QUOTE_PROMPT', self.system_prompt)
        prompt = f"{quote_prompt_base}\n\n인용할 트윗 내용: \"{tweet_text}\"{keywords_text}\n\n너의 한국어 인용 코멘트:"
        if detected_language == 'english':
            prompt = f"""You are a friendly 20-something Korean guy quoting a tweet. Write a casual English comment for this tweet. Tweet to quote: "{tweet_text}"{keywords_text}\n\nYour English quote comment:"""
            
        quote_text = self._generate_with_retry(prompt)
        if quote_text:
            quote_text = self.clean_text(quote_text) if detected_language == 'korean' else quote_text.strip()
            quote_text = self.ensure_keywords_included(quote_text, detected_language)
            print(f"Generated quote text ({detected_language}, {len(quote_text)} chars): {quote_text}")
            return quote_text
        return None

    def like_tweet(self, tweet_element):
        """Like a tweet."""
        try:
            like_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="like"]')
            if self.human_like_click(like_button): print("✅ Tweet liked successfully!")
        except: pass

    def retweet_tweet(self, tweet_element):
        """Retweet a tweet."""
        try:
            retweet_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="retweet"]')
            if self.human_like_click(retweet_button):
                retweet_option = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="retweetConfirm"]')))
                if self.human_like_click(retweet_option): print("✅ Tweet retweeted successfully!")
        except: pass

    def quote_tweet(self, tweet_element, tweet_text):
        """Create a quote tweet."""
        try:
            quote_text = self.generate_quote_text(tweet_text)
            if not quote_text or self.bot_should_stop: return False
            
            tweet_id = self.get_tweet_id(tweet_element)
            if not tweet_id: return False
            
            fresh_tweet_element = self.wait.until(EC.presence_of_element_located((By.XPATH, f'//a[contains(@href, "{tweet_id.split("/")[-1]}")]/ancestor::article[@data-testid="tweet"]')))
            
            quote_button = fresh_tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="retweet"]')
            self.human_like_click(quote_button)
            
            quote_option = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Quote') or contains(text(), '인용')]")))
            self.human_like_click(quote_option)
            
            quote_text_area = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')))
            self.type_like_human(quote_text_area, quote_text)
            
            quote_submit_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="tweetButton"]')))
            self.human_like_click(quote_submit_button)
            
            WebDriverWait(self.driver, 10).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')))
            print("✅ Quote tweet posted successfully!")
            return True
        except Exception as e:
            print(f"❌ Error creating quote tweet: {str(e)}")
            try:
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except: pass
            return False

    def reply_to_tweet(self, tweet_element):
        """Reply to a specific tweet."""
        try:
            self.simulate_reading_behavior(tweet_element)
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet_element)
            self.random_delay(0.5, 1)

            tweet_id = self.get_tweet_id(tweet_element)
            tweet_text = self.get_tweet_text(tweet_element)
            if not tweet_id or not tweet_text: return "PREP_FAILED"
            if self.search_mode and self.current_keyword and not self.contains_keyword(tweet_text, self.current_keyword): return "PREP_FAILED"
            
            reply_text = self.generate_ai_response(tweet_text)
            if not reply_text or self.bot_should_stop: return "PREP_FAILED"
            
            reply_button = tweet_element.find_element(By.CSS_SELECTOR, '[data-testid="reply"]')
            self.human_like_click(reply_button)
            
            reply_box_selector = (By.CSS_SELECTOR, '[data-testid="tweetTextarea_0"]')
            reply_box = self.wait.until(EC.presence_of_element_located(reply_box_selector))
            self.type_like_human(reply_box, reply_text)
            
            submit_button = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="tweetButton"]')))
            self.human_like_click(submit_button)
            
            print("Waiting for reply to be posted...")
            
            try:
                WebDriverWait(self.driver, 10).until(EC.invisibility_of_element_located(reply_box_selector))
                print("✅ Reply successfully posted.")
                if random.random() < 0.8: self.like_tweet(tweet_element)
                if random.random() < 0.5: self.retweet_tweet(tweet_element)
                return "SUCCESS"
            except TimeoutException:
                print("❌ Reply post failed!")
                try: ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
                except: pass
                return "POST_FAILED"
        except Exception as e:
            print(f"❌ Error preparing or sending reply: {str(e)}")
            try: ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except: pass
            return "PREP_FAILED"

    def scroll_feed(self, scroll_count=3):
        """Scroll the feed to load more tweets."""
        for _ in range(scroll_count):
            self.driver.execute_script(f"window.scrollBy(0, {random.randint(500, 1000)})")

    def get_all_visible_tweets(self):
        """Get all currently visible tweets on the page."""
        try:
            all_tweets = self.driver.find_elements(By.CSS_SELECTOR, 'article[data-testid="tweet"]')
            return [t for t in all_tweets if t.is_displayed() and not self.is_own_tweet(t) and not self.is_reply_tweet(t)]
        except: return []

    # --- [MODIFIED] Main loop with randomized action order and delays ---
    def monitor_feed(self, interval=3):
        """Monitor the feed with randomized, human-like interaction patterns."""
        processed_tweets = self.load_processed_tweets()
        print(f"✅ Loaded {len(processed_tweets)} previously processed tweet IDs.")
        
        location = "home feed"
        if self.search_mode: location = f"search results for '{self.current_keyword}'"
        elif self.community_url: location = "community"
            
        print(f"🔍 Monitoring: {location}")
        print(f"🔄 API Key Rotation: Enabled with {len(self.gemini_api_keys)} key(s).")
        if self.required_keywords: print(f"🎯 Required Keywords: {self.required_keywords}")
        
        consecutive_no_new_tweets = 0
        
        while not self.bot_should_stop:
            try:
                tweets = self.get_all_visible_tweets()
                new_tweets_found = False
                
                for tweet in tweets:
                    if self.bot_should_stop: break
                    
                    tweet_id = self.get_tweet_id(tweet)
                    if not tweet_id or tweet_id in processed_tweets:
                        continue
                        
                    new_tweets_found = True
                    print(f"\nProcessing new tweet: {tweet_id}")
                    
                    # --- [NEW FEATURE] Randomize action order ---
                    actions = ["reply", "quote"]
                    random.shuffle(actions)
                    first_action_name, second_action_name = actions[0], actions[1]
                    
                    first_action_success = False
                    
                    # --- Execute First Action ---
                    print(f"🤖 First action: {first_action_name.capitalize()}")
                    if first_action_name == "reply":
                        status = self.reply_to_tweet(tweet)
                        if status == "SUCCESS":
                            first_action_success = True
                    elif first_action_name == "quote":
                        tweet_text = self.get_tweet_text(tweet)
                        if tweet_text and self.quote_tweet(tweet, tweet_text):
                            first_action_success = True

                    # --- If First Action Succeeded, Proceed to Second ---
                    if first_action_success:
                        # --- [NEW FEATURE] Human-like delay between actions ---
                        human_delay = round(random.uniform(1.0, 3.0), 3)
                        print(f"⏳ Human-like pause for {human_delay} seconds...")
                        time.sleep(human_delay)
                        
                        # --- Execute Second Action ---
                        print(f"🤖 Second action: {second_action_name.capitalize()}")
                        if second_action_name == "reply":
                            self.reply_to_tweet(tweet) # We don't need to check status as the main job is done
                        elif second_action_name == "quote":
                            tweet_text = self.get_tweet_text(tweet)
                            if tweet_text:
                                self.quote_tweet(tweet, tweet_text)
                        
                        processed_tweets.add(tweet_id)
                        print(f"✅ Full cycle completed for tweet: {tweet_id}")
                        
                        # Wait for the next cycle
                        delay = random.uniform(10, 18)
                        print(f"⚡ HYPER SPEED: Waiting {delay:.0f} seconds for the next tweet...")
                        time.sleep(delay)
                    else:
                        print(f"⚠️ First action ({first_action_name}) failed. Skipping tweet to avoid errors.")
                        processed_tweets.add(tweet_id) # Add to processed to avoid retrying a failed tweet

                if self.bot_should_stop: break
                
                if new_tweets_found:
                    self.save_processed_tweets(processed_tweets)
                    consecutive_no_new_tweets = 0
                else:
                    consecutive_no_new_tweets += 1
                    print(f"No new tweets found ({consecutive_no_new_tweets} consecutive times). Aggressively scrolling...")
                    self.scroll_feed(scroll_count=min(5 + consecutive_no_new_tweets, 15))
                
                if len(processed_tweets) > 300:
                    processed_tweets = set(list(processed_tweets)[-300:])
                    self.save_processed_tweets(processed_tweets)
                
                time.sleep(random.uniform(interval * 0.8, interval * 1.1))
                
            except Exception as e:
                print(f"An error occurred in the main loop: {str(e)}. Recovering...")
                self.scroll_feed(scroll_count=10)
        
        print("🔄 Final cleanup before shutdown...")
        self.save_processed_tweets(processed_tweets)
        print("✅ Processed tweets saved")

    def cleanup(self):
        """Close the browser and clean up"""
        print("🧹 Cleaning up resources...")
        if hasattr(self, 'driver'):
            self.driver.quit()
        print("✅ Cleanup completed")

def get_required_keywords():
    """Get required keywords that must be included in all responses"""
    print("\n" + "="*60 + "\n📝 필수 키워드 설정 (Required Keywords Setup)\n" + "="*60)
    keywords_input = input("모든 답변에 포함될 키워드를 콤마(,)로 구분해 입력하세요 (없으면 Enter): ").strip()
    if not keywords_input:
        print("✅ 필수 키워드 없이 진행합니다.")
        return []
    keywords = [kw.strip() for kw in keywords_input.split(',') if kw.strip()]
    print(f"✅ 설정된 필수 키워드: {keywords}")
    return keywords

def get_user_choice():
    """Get user's choice for monitoring mode"""
    print("\n" + "="*60 + "\n🤖 Twitter Bot - HYPER SPEED MODE\n" + "="*60)
    print("1. 홈 피드 모니터링 (Home Feed Monitoring)")
    print("2. 커뮤니티 모니터링 (Community Monitoring)")  
    print("3. 키워드 검색 모니터링 (Keyword Search Monitoring)")
    print("="*60)
    while True:
        choice = input("\n선택하세요 (Choose an option) [1-3]: ").strip()
        if choice in ['1', '2', '3']: return int(choice)
        else: print("❌ 1-3 사이의 번호를 입력하세요.")

def get_search_keyword():
    """Get search keyword from user"""
    print("\n" + "="*50 + "\n🔍 키워드 검색 모드 (Keyword Search Mode)\n" + "="*50)
    while True:
        keyword = input("검색할 키워드를 입력하세요: ").strip()
        if keyword: return keyword
        else: print("❌ 키워드를 입력해주세요.")

def main():
    print("🤖 Twitter Bot - HYPER SPEED MODE Starting...")
    
    required_keywords = get_required_keywords()
    choice = get_user_choice()
    
    bot = None
    try:
        bot = TwitterBot()
        bot.required_keywords = required_keywords
        
        if choice == 1:
            bot.search_mode = False
            bot.community_url = None
        elif choice == 2:
            bot.search_mode = False
        else:
            keyword = get_search_keyword()
            bot.search_mode = True
            bot.current_keyword = keyword
            bot.community_url = None
        
        login_success = False
        for attempt in range(3):
            print(f"\n🔐 로그인 시도 {attempt + 1}/3")
            if attempt > 0:
                retry_choice = input("다시 시도하기 전 옵션 선택 [1: 쿠키 삭제 후 재시도, 2: 그냥 재시도, 3: 종료]: ").strip()
                if retry_choice == '1': bot.clear_login_data()
                elif retry_choice == '3': return
            
            if bot.login():
                login_success = True
                break
            elif attempt < 2:
                print("❌ 로그인 실패. 잠시 후 다시 시도합니다.")
                time.sleep(3)
        
        if not login_success:
            print("❌ 모든 로그인 시도가 실패했습니다. .env 파일과 계정 상태를 확인해주세요.")
            return
        
        print("\n" + "🚀"*20 + "\nHYPER SPEED MODE + API KEY ROTATION ACTIVATED!\n" + "🚀"*20)
        bot.monitor_feed(interval=2)
        
    except KeyboardInterrupt:
        print("\n🛑 키보드 인터럽트 감지 - 봇 종료 중...")
        if bot: bot.bot_should_stop = True
    except Exception as e:
        print(f"\n💥 예상치 못한 오류 발생: {str(e)}")
        if bot: bot.bot_should_stop = True
    finally:
        if bot: bot.cleanup()
        print("👋 HYPER SPEED 봇 종료 완료!")
        sys.exit(0)

if __name__ == "__main__":
    main()
