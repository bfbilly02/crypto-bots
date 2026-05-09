#!/usr/bin/env python3
"""
CARTE Credit Auto-Claim Bot v1
Credits: bot by billy (ethjup)
24/7 auto-claim credits when available

Usage:
  python3 carte_bot.py                    → interactive menu
  python3 carte_bot.py --start             → start mining immediately
  python3 carte_bot.py --auth              → auth setup (import session)
"""

import json, time, sys, os, subprocess, threading
from pathlib import Path
from datetime import datetime

# ── Config ──────────────────────────────────────────────────
SESSION_FILE   = Path.home() / ".carte-bot/session.json"
AUTH_TOKEN_URL = "https://manideck.api.manifoldxyz.dev/api/auth/refresh"
API_BASE       = "https://manideck.api.manifoldxyz.dev/api/v1"
MANIFOLD_AUTH  = "manideck-auth"
COOKIE_FILE    = Path.home() / ".carte-bot/raw_auth.json"

# ── Style ────────────────────────────────────────────────────
BOLD   = "\033[1m"
RESET  = "\033[0m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
MAG    = "\033[95m"
GRAY   = "\033[90m"

def p(msg, color=""):
    prefix = {"red": RED, "green": GREEN, "yellow": YELLOW, "blue": BLUE,
              "cyan": CYAN, "mag": MAG, "gray": GRAY}.get(color, "")
    print(f"{prefix}{msg}{RESET}")

def bold(msg): return f"{BOLD}{msg}{RESET}"
def dim(msg): return f"{GRAY}{msg}{RESET}"

# ── Header ───────────────────────────────────────────────────
HEADER = f"""
{bold('╔══════════════════════════════════════════════════════════╗')}
{bold('║')}  {bold('CARTE Credit Bot')}   {dim('v1.0')}                        {bold('║')}
{bold('║')}  {dim('Auto-claim credits • Credits: billy (ethjup)')}       {bold('║')}
{bold('╚══════════════════════════════════════════════════════════╝')}"""

MENU = f"""
{dim('─' * 56)}
{dim('  Credit: billy (ethjup)')}
{dim('─' * 56 )}
  {CYAN}1.{RESET}  Start Bot        {CYAN}2.{RESET}  Check Balance
  {CYAN}3.{RESET}  Auth Setup       {CYAN}4.{RESET}  Status / Stats
  {RED}5.{RESET}  Exit

{dim('─' * 56)}"""

# ── Session / Auth ────────────────────────────────────────────
def save_session(data):
    os.makedirs(SESSION_FILE.parent, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2))

def load_session():
    if not SESSION_FILE.exists():
        return None
    return json.loads(SESSION_FILE.read_text())

def save_raw_auth(data):
    os.makedirs(COOKIE_FILE.parent, exist_ok=True)
    COOKIE_FILE.write_text(json.dumps(data, indent=2))

def load_raw_auth():
    if not COOKIE_FILE.exists():
        return None
    return json.loads(COOKIE_FILE.read_text())

# ── API helpers ───────────────────────────────────────────────
def api_call(method, path, token=None, json_data=None, timeout=30):
    """Make API call via Manifold backend."""
    url = f"{API_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    cmd = ["curl", "-s", "--max-time", str(timeout), "-X", method,
           "-H", f"Content-Type: application/json"]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    if json_data:
        cmd += ["-d", json.dumps(json_data)]
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"curl error: {result.stderr.strip()}")
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"Invalid JSON: {result.stdout[:100]}")

def parse_jwt_exp(token: str) -> int:
    """Extract exp from JWT."""
    try:
        parts = token.split(".")
        payload = parts[1] + "=="
        import base64
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded.decode("latin-1"))
        return data.get("exp", 0)
    except:
        return 0

def is_token_expired(token: str, margin=60) -> bool:
    exp = parse_jwt_exp(token)
    if exp == 0:
        return True
    return exp * 1000 - time.time() * 1000 < margin * 1000

# ── Token refresh ─────────────────────────────────────────────
def refresh_tokens(session: dict) -> dict:
    """Refresh access + refresh tokens."""
    refresh = session.get("refreshToken")
    if not refresh:
        raise RuntimeError("No refresh token")

    data = api_call("POST", "/auth/refresh",
                    json_data={"refreshToken": refresh})
    if "accessToken" in data:
        session["accessToken"] = data["accessToken"]
        session["refreshToken"] = data.get("refreshToken", refresh)
        session["refreshed_at"] = time.time()
        save_session(session)
        return session
    raise RuntimeError(f"Refresh failed: {data}")

def get_valid_token(session: dict) -> str:
    """Return a valid access token, refreshing if needed."""
    token = session.get("accessToken", "")
    if not token or is_token_expired(token):
        session = refresh_tokens(session)
        token = session.get("accessToken", "")
    return token

# ── Credit check ─────────────────────────────────────────────
def get_credit_balance(session: dict):
    token = get_valid_token(session)
    return api_call("GET", "/credits/balance", token=token)

def claim_credits(session: dict):
    token = get_valid_token(session)
    return api_call("POST", "/credits/claim-regen", token=token)

# ── Bot State ────────────────────────────────────────────────
class Bot:
    def __init__(self):
        self.running    = False
        self.paused     = False
        self.total_claimed = 0
        self.total_check  = 0
        self.last_check   = None
        self.last_claim   = None
        self.start_time   = None
        self.claimed_this_session = 0
        self.errors       = []

    def record_claim(self, amount: int):
        self.total_claimed += amount
        self.claimed_this_session += amount
        self.last_claim = time.time()

    def record_check(self):
        self.last_check = time.time()
        self.total_check += 1

    def record_error(self, err: str):
        self.errors.append({"t": time.time(), "e": err})
        if len(self.errors) > 50:
            self.errors = self.errors[-50:]

    def status_summary(self) -> dict:
        elapsed = time.time() - (self.start_time or time.time())
        h, m, s = int(elapsed//3600), int((elapsed%3600)//60), int(elapsed%60)
        rate = self.total_claimed / (elapsed/3600) if elapsed > 60 else 0
        return {
            "h": h, "m": m, "s": s,
            "total": self.total_claimed,
            "session": self.claimed_this_session,
            "checks": self.total_check,
            "rate": rate,
            "paused": self.paused,
        }

# ── Reporter ────────────────────────────────────────────────
def report_status(bot: Bot, balance_data: dict = None):
    s = bot.status_summary()
    now = time.strftime("%H:%M:%S")

    lines = []
    lines.append(dim("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    lines.append(f"💎 {bold('CARTE Status')}  `{now}`  {dim('• bot by billy (ethjup)')}")
    lines.append(dim("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    lines.append(f"  💰 balance  : `{balance_data.get('balance', 0) if balance_data else '?'}`")
    lines.append(f"  🎁 claimable: `{balance_data.get('claimable', 0) if balance_data else '?'}`")
    lines.append(f"  ⚡ max      : `{balance_data.get('maxFreeBalance', '?') if balance_data else '?'}`")
    lines.append(f"  ⛏ claimed   : `#{s['total']}` (session: `+{s['session']}`)")
    lines.append(f"  📊 checks   : `{s['checks']}`")
    lines.append(f"  ⏱ uptime    : `{s['h']}h {s['m']}m {s['s']}s`")
    lines.append(f"  🔄 rate/hr  : `{s['rate']:.1f}` claims/hr")
    status = "⏸ PAUSED" if s['paused'] else "🟢 RUNNING"
    lines.append(f"  🔖 status   : {status}")
    if bot.errors:
        last_err = bot.errors[-1]
        ts = datetime.fromtimestamp(last_err['t']).strftime("%H:%M:%S")
        lines.append(f"  ⚠ last err : [{ts}] {last_err['e'][:50]}")
    lines.append(dim("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
    print("\n".join(lines), flush=True)

# ── Status reporter thread ────────────────────────────────────
def status_reporter(bot: Bot, get_balance_fn):
    """Print full status every 60s."""
    while bot.running:
        time.sleep(60)
        if not bot.running:
            break
        try:
            session = load_session()
            if session:
                bal = get_balance_fn(session)
                report_status(bot, bal)
        except:
            pass

# ── Main mining loop ─────────────────────────────────────────
def run_bot(bot: Bot):
    print(f"{GREEN}✅ Auth OK{RESET}  Starting CARTE credit bot...")
    print(f"{CYAN}⏱  Auto-claim every 60s • Credits: billy (ethjup){RESET}\n")

    # Start status reporter
    threading.Thread(target=status_reporter,
                    args=(bot, get_credit_balance),
                    daemon=True).start()

    session = load_session()

    while bot.running:
        if bot.paused:
            time.sleep(5)
            continue

        try:
            bal = get_credit_balance(session)
            bot.record_check()

            balance  = bal.get("balance", 0)
            claimable = bal.get("claimable", 0)
            max_bal  = bal.get("maxFreeBalance", 50)

            # Check if we should claim
            if claimable > 0:
                print(f"\n{YELLOW}🎁 Claimable: {claimable} credits → Claiming...{RESET}")
                result = claim_credits(session)
                if result and result.get("claimed", 0) > 0:
                    amt = result.get("claimed", claimable)
                    bot.record_claim(amt)
                    new_bal = bal.get("balance", 0) + amt
                    print(f"{GREEN}✅ Claimed +{amt}{RESET}  |  Balance now: {new_bal}/{max_bal}")
                elif result and result.get("claimed") == 0:
                    print(f"{YELLOW}⚠ Nothing to claim (maybe already claimed)")

                # Refresh session if needed
                session = load_session()

            # Also claim drip credits when balance is low but claimable exists
            elif balance < max_bal and claimable == 0:
                # No claimable right now — just wait
                pass

            time.sleep(60)

        except RuntimeError as e:
            err = str(e)
            bot.record_error(err)
            # Try to refresh token
            try:
                session = refresh_tokens(session)
            except:
                pass
            time.sleep(15)
        except Exception as e:
            bot.record_error(str(e))
            time.sleep(15)

# ── Interactive Auth Setup ────────────────────────────────────
def auth_setup():
    print(f"\n{CYAN}🔑 Auth Setup{RESET}")
    print(dim("─" * 50))
    print("""
  To authenticate, we need your Manifold session tokens.
  Steps:

  1. Open https://carte.gg in Chrome (logged in with your wallet)
  2. Open DevTools (F12) → Console
  3. Run this command:

    JSON.stringify(localStorage.getItem('manideck-auth'))

  4. Copy the output (starts with {"accessToken":...)
  5. Paste it here

  The bot will auto-refresh tokens when expired.
  No private keys stored.
""")
    print(dim("─" * 50))
    try:
        raw = input(f"  {CYAN}▶ Paste manideck-auth JSON:{RESET}  ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{YELLOW}Cancelled.{RESET}")
        return

    if not raw:
        print(f"{RED}❌ Empty input.{RESET}")
        return

    try:
        auth_data = json.loads(raw)
        if not auth_data.get("accessToken"):
            raise ValueError("No accessToken")
        # Save raw auth data
        save_raw_auth(auth_data)

        session = {
            "accessToken": auth_data["accessToken"],
            "refreshToken": auth_data.get("refreshToken", ""),
            "user": auth_data.get("user", {}),
            "saved_at": time.time(),
            "refreshed_at": time.time(),
        }
        save_session(session)

        # Test: verify token works
        token = get_valid_token(session)
        bal = get_credit_balance(session)
        print(f"\n{GREEN}✅ Auth OK!{RESET}  Balance: {bal.get('balance', '?')}, "
              f"Claimable: {bal.get('claimable', '?')}")
    except Exception as e:
        print(f"{RED}❌ Auth failed: {e}{RESET}")
        print(f"{YELLOW}Make sure you pasted the correct JSON from localStorage.{RESET}")

def show_status(bot: Bot):
    s = bot.status_summary()
    session = load_session()
    bal = None
    if session:
        try:
            bal = get_credit_balance(session)
        except:
            pass

    print()
    if not session:
        print(f"{RED}❌ Not authenticated. Use option 3 to set up auth.{RESET}")
        return

    print(f"{GREEN}✅ Authenticated{RESET}")
    if bal:
        print(f"   💰 Balance: {bal.get('balance', 0)} / {bal.get('maxFreeBalance', 50)}")
        print(f"   🎁 Claimable: {bal.get('claimable', 0)}")
        if bal.get("dripIntervalSeconds"):
            print(f"   ⏱ Drip interval: {bal['dripIntervalSeconds']}s")
    print()
    print(f"   ⛏ Total claimed: #{s['total']}")
    print(f"   📊 Total checks: {s['checks']}")
    print(f"   ⏱ Uptime: {s['h']}h {s['m']}m {s['s']}s")
    print(f"   🔖 Rate: {s['rate']:.1f} claims/hr")
    print(f"   🔄 Status: {'PAUSED' if s['paused'] else 'RUNNING'}")
    if bot.errors:
        print(f"   ⚠ Recent errors: {len(bot.errors)}")
    print()

def check_balance():
    session = load_session()
    if not session:
        print(f"{RED}❌ Not authenticated.{RESET}")
        return
    try:
        bal = get_credit_balance(session)
        print(f"\n{GREEN}💰 Balance: {bal.get('balance', 0)} / {bal.get('maxFreeBalance', 50)}{RESET}")
        print(f"{YELLOW}🎁 Claimable: {bal.get('claimable', 0)}{RESET}")
        if bal.get("dripIntervalSeconds"):
            next_drip = bal.get("dripIntervalSeconds", 0)
            print(f"{CYAN}⏱ Next drip in: {next_drip}s{RESET}")
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")

# ── Main ─────────────────────────────────────────────────────
def main():
    global_bot = Bot()

    print(HEADER)

    while True:
        print(MENU)
        try:
            choice = input(f"  {CYAN}▶ Enter choice (1-5):{RESET}  ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n\n{YELLOW}👋 Bye!{RESET}")
            sys.exit(0)

        if choice == "1":
            session = load_session()
            if not session:
                print(f"\n{RED}❌ Not authenticated. Use option 3 first.{RESET}\n")
                time.sleep(2)
                continue

            print(f"\n{GREEN}🚀 Starting CARTE credit bot...{RESET}")
            print(f"{CYAN}   Press Ctrl+C to stop.{RESET}\n")
            global_bot.running = True
            global_bot.start_time = time.time()

            try:
                run_bot(global_bot)
            except KeyboardInterrupt:
                global_bot.running = False
                print(f"\n\n{YELLOW}⏹ Bot stopped.{RESET}")
                print(f"   Total claimed this session: +{global_bot.claimed_this_session}")
                print(f"   Total all time: #{global_bot.total_claimed}\n")
                time.sleep(1)

        elif choice == "2":
            check_balance()

        elif choice == "3":
            auth_setup()

        elif choice == "4":
            show_status(global_bot)

        elif choice == "5":
            print(f"\n{GREEN}👋 Bye! Credits: billy (ethjup){RESET}\n")
            sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Interrupted.{RESET}")
        sys.exit(0)