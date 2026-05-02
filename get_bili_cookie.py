import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

CHROME_PROFILE = Path.home() / "AppData/Local/Google/Chrome/User Data"
EDGE_PROFILE = Path.home() / "AppData/Local/Microsoft/Edge/User Data"
OUTPUT = Path(__file__).parent / "bilibili_cookies.txt"


def to_netscape(cookies):
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expiry = str(int(c.get("expires", 0)))
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
    return "\n".join(lines)


async def try_profile(profile_path, name):
    if not profile_path.exists():
        return None
    print(f"Trying {name} profile: {profile_path}")
    try:
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                str(profile_path),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto("https://www.bilibili.com", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Check login status
            cookies = await ctx.cookies("https://www.bilibili.com")
            bili_cookies = [c for c in cookies if "bilibili" in c.get("domain", "")]
            sessdata = [c for c in bili_cookies if c.get("name") == "SESSDATA"]

            if sessdata and sessdata[0].get("value"):
                print(f"  [OK] {name}: Logged in. Found {len(bili_cookies)} bilibili cookies.")
                netscape = to_netscape(bili_cookies)
                OUTPUT.write_text(netscape, encoding="utf-8")
                print(f"  [Saved] {OUTPUT}")
                await ctx.close()
                return bili_cookies
            else:
                print(f"  [NO] {name}: Not logged in.")
                await ctx.close()
                return None
    except Exception as e:
        print(f"  [ERR] {name} failed: {e}")
        return None


async def manual_login():
    """Open browser for user to manually log in."""
    print("Opening Bilibili login page...")
    print("Please log in manually (scan QR code or enter password).")
    print("The browser will close automatically after login is detected.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto("https://passport.bilibili.com/login")

        # Wait for login
        for i in range(300):  # max 5 minutes
            await asyncio.sleep(1)
            cookies = await ctx.cookies("https://www.bilibili.com")
            sessdata = [c for c in cookies if c.get("name") == "SESSDATA"]
            if sessdata and sessdata[0].get("value"):
                print("Login detected!")
                bili_cookies = [c for c in cookies if "bilibili" in c.get("domain", "")]
                netscape = to_netscape(bili_cookies)
                OUTPUT.write_text(netscape, encoding="utf-8")
                print(f"Saved to: {OUTPUT}")
                await browser.close()
                return bili_cookies

        print("Timeout: login not detected within 5 minutes.")
        await browser.close()
        return None


async def main():
    # Try existing profiles first
    result = await try_profile(CHROME_PROFILE, "Chrome")
    if not result:
        result = await try_profile(EDGE_PROFILE, "Edge")

    if not result:
        print()
        print("No logged-in Bilibili account found in browser profiles.")
        print("Opening browser for manual login...")
        result = await manual_login()
    return bool(result)


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
