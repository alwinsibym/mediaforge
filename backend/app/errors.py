"""Error codes and plain-English explanations.

Every problem the person can see is described the same way: a short title, one sentence on what
went wrong, then what happened, the likely reasons, and what to do next. The original technical
message is kept for anyone who wants it.
"""

CATALOG: dict[str, dict] = {
    "MF-NET-01": {
        "title": "Can't find the site",
        "summary": "This computer could not look up the site's address.",
        "what": "MediaForge asked your network for the site's address and got no answer, so it "
        "could not even start talking to the site.",
        "why": [
            "Your internet connection is off or unstable.",
            "Your DNS (the network's address book) is slow or blocking that site.",
            "A VPN, firewall or your internet provider is blocking the site.",
        ],
        "fix": [
            "Check that other websites open in your browser.",
            "Turn a VPN off (or on, if the site is blocked where you live) and try again.",
            "Change your DNS to 1.1.1.1 or 8.8.8.8 in your network settings.",
            "If a playlist stopped, use Retry or Resume once the connection is back.",
        ],
    },
    "MF-NET-02": {
        "title": "The site did not answer",
        "summary": "The connection to the site timed out.",
        "what": "MediaForge reached out to the site but waited too long for a reply.",
        "why": [
            "The site is down or very slow right now.",
            "Your network, VPN or firewall is quietly blocking it.",
            "Your internet is too slow or unstable.",
        ],
        "fix": [
            "Check that the site opens in your browser.",
            "Try again in a few minutes.",
            "Turn off a VPN or firewall that may be blocking it.",
        ],
    },
    "MF-NET-03": {
        "title": "The site closed the connection",
        "summary": "The site hung up while MediaForge was loading its page.",
        "what": "The connection was made, then the site (or something between you and it) cut it "
        "off. Windows calls this error 10054.",
        "why": [
            "The site blocks automated downloaders.",
            "A VPN, antivirus web protection or firewall is cutting the connection.",
            "Your internet provider blocks the site.",
        ],
        "fix": [
            "Turn off your VPN and your antivirus web shield, then try again.",
            "If the site is blocked in your country, turn a VPN on instead.",
            "Choose your browser under Settings so requests carry a normal sign-in.",
            "Update yt-dlp from Settings.",
        ],
    },
    "MF-SITE-01": {
        "title": "The site wants proof you are a person",
        "summary": "The site is asking to confirm that this is not a bot.",
        "what": "YouTube (or a similar site) noticed many automatic requests and now asks the "
        "visitor to sign in before it will serve videos.",
        "why": [
            "Downloading many videos quickly looks automatic to the site.",
            "You are not signed in, so the site trusts the request less.",
            "Your network address was used by others for many downloads.",
        ],
        "fix": [
            "Open Settings and choose the browser where you are signed in (Firefox is the most "
            "reliable).",
            "Set playlist videos at the same time to 1.",
            "Wait a few minutes, then use Retry or Resume.",
        ],
    },
    "MF-SITE-02": {
        "title": "This needs you to be signed in",
        "summary": "The site only shows this to signed-in visitors.",
        "what": "The page exists, but the site hides the video from visitors who are not signed "
        "in, usually because it is age-restricted, sensitive, private or members-only.",
        "why": [
            "The post or video is marked adult or sensitive.",
            "It is private, or limited to followers or members.",
            "The site requires an account for everything.",
        ],
        "fix": [
            "Sign in to the site in Firefox, then choose Firefox under Settings.",
            "Or export a cookies.txt file from your browser and choose it under Settings.",
            "Make sure the account you used is allowed to see the video.",
        ],
    },
    "MF-SITE-03": {
        "title": "The site refused the download",
        "summary": "The site answered with an access error (HTTP 403 Forbidden).",
        "what": "The site understood the request and refused it. Without a sign-in, some sites "
        "(Reddit is a common one) refuse downloaders, and YouTube sometimes refuses one request "
        "for a moment.",
        "why": [
            "The site blocks requests that are not from a signed-in browser.",
            "Your network address is being limited.",
            "yt-dlp is out of date and the site changed.",
        ],
        "fix": [
            "Try again in a moment. MediaForge already retried a few times.",
            "Choose your browser under Settings, so requests carry your sign-in.",
            "Update yt-dlp from Settings.",
            "Turn a VPN off or on and try again.",
        ],
    },
    "MF-SITE-04": {
        "title": "No video found",
        "summary": "That page has no video MediaForge can reach.",
        "what": "The link opened, but the site did not offer any video or audio to download.",
        "why": [
            "The post has only text or pictures (MediaForge saves video and audio, not images).",
            "The video belongs to a quoted or replied-to post.",
            "The site hides adult or sensitive videos from visitors who are not signed in.",
        ],
        "fix": [
            "Open the link in your browser and check that it really plays a video.",
            "If the video is in a quoted post, paste that post's link instead.",
            "For adult or sensitive posts, choose your browser under Settings.",
        ],
    },
    "MF-SITE-05": {
        "title": "Video not available",
        "summary": "The video is private, removed or not available.",
        "what": "The site says this video can't be played. It may have been deleted or made "
        "private, or the link may be wrong.",
        "why": [
            "The owner removed it or made it private.",
            "The link is incomplete or mistyped.",
            "It is blocked in your country or for your account.",
        ],
        "fix": [
            "Open the link in your browser to check that it plays.",
            "Copy the link again from the address bar.",
            "If it only works when signed in, choose your browser under Settings.",
        ],
    },
    "MF-SITE-06": {
        "title": "That site is not supported",
        "summary": "MediaForge does not know how to download from this link.",
        "what": "yt-dlp, the downloader inside MediaForge, has no support for this address.",
        "why": [
            "The site is not in yt-dlp's list.",
            "The link is a home page, a search page or a feed instead of one video.",
            "yt-dlp is out of date.",
        ],
        "fix": [
            "Paste the link of the page that plays the one video.",
            "Update yt-dlp from Settings.",
            "Check yt-dlp's list of supported sites on GitHub.",
        ],
    },
    "MF-SITE-07": {
        "title": "Not available in your region",
        "summary": "The site blocks this video where you are.",
        "what": "The owner or the site allows this video only in certain countries.",
        "why": ["The video is licensed for other regions only."],
        "fix": [
            "Use a VPN set to an allowed country, then try again.",
            "Check whether the video plays in your browser.",
        ],
    },
    "MF-SITE-08": {
        "title": "Too many requests",
        "summary": "The site is asking MediaForge to slow down (HTTP 429).",
        "what": "The site limits how many requests one visitor can make in a short time.",
        "why": ["Many videos were requested quickly."],
        "fix": [
            "Wait several minutes, then use Retry or Resume.",
            "Set playlist videos at the same time to 1 under Settings.",
            "Choose your browser under Settings so the site recognises you.",
        ],
    },
    "MF-COOK-01": {
        "title": "Could not read your browser sign-in",
        "summary": "MediaForge could not use the cookies from your browser.",
        "what": "To use your sign-in, MediaForge reads your browser's cookie file. Chrome and "
        "Edge lock that file while they run, and recent versions also encrypt it.",
        "why": [
            "Chrome or Edge is open and has the file locked.",
            "Recent Chrome and Edge versions block other programs from reading it.",
        ],
        "fix": [
            "Use Firefox: sign in there, then choose Firefox under Settings.",
            "Or export a cookies.txt file (the 'Get cookies.txt LOCALLY' extension works) and "
            "choose it under Settings.",
            "If you stay with Chrome, close it completely first, including the tray icon.",
        ],
    },
    "MF-LIM-01": {
        "title": "Live streams are not supported",
        "summary": "This video is live right now.",
        "what": "MediaForge only converts videos that have ended, because a live stream has no "
        "end to download.",
        "why": ["The broadcast has not finished."],
        "fix": ["Try again after the stream ends and the recording is available."],
    },
    "MF-LIM-02": {
        "title": "Video is too long",
        "summary": "The video is longer than the limit MediaForge allows.",
        "what": "To protect your disk and time, MediaForge refuses very long videos.",
        "why": ["The limit is one hour unless you raised it."],
        "fix": [
            "Use Start and Stop under More options to download only part of it.",
            "Or raise MEDIAFORGE_MAX_DURATION (in seconds) and restart.",
        ],
    },
    "MF-LIM-03": {
        "title": "File is too large",
        "summary": "The uploaded file is bigger than the allowed size.",
        "what": "MediaForge refuses uploads above its size limit.",
        "why": ["The limit protects your disk and memory."],
        "fix": ["Use a smaller file, or raise MEDIAFORGE_MAX_UPLOAD_MB and restart."],
    },
    "MF-TOOL-01": {
        "title": "FFmpeg is missing",
        "summary": "FFmpeg was not found on this computer.",
        "what": "FFmpeg joins video with audio and converts formats. Without it, MediaForge "
        "cannot finish a download.",
        "why": ["FFmpeg is not installed, or it is not on this computer's PATH."],
        "fix": [
            "Install it (Windows: winget install Gyan.FFmpeg), open a new terminal and restart "
            "MediaForge.",
            "Or set MEDIAFORGE_FFMPEG_DIR to the folder that contains ffmpeg.exe.",
        ],
    },
    "MF-TOOL-02": {
        "title": "FFmpeg could not convert the file",
        "summary": "The conversion step failed.",
        "what": "FFmpeg started the conversion but stopped with an error.",
        "why": [
            "The source file is damaged or unusual.",
            "The disk is full or the folder is not writable.",
        ],
        "fix": [
            "Try another quality or format.",
            "Check free disk space.",
            "Try again; if it keeps failing, note the technical details below.",
        ],
    },
    "MF-TOOL-03": {
        "title": "No file was produced",
        "summary": "The download finished but no output file appeared.",
        "what": "Everything ran, but the result file is missing.",
        "why": ["An antivirus may have removed it.", "The disk may be full."],
        "fix": ["Check free disk space and antivirus quarantine, then try again."],
    },
    "MF-TOOL-04": {
        "title": "The conversion took too long",
        "summary": "MediaForge stopped a conversion that was not finishing.",
        "what": "A safety timeout ended the conversion.",
        "why": ["The file is very large, or the computer is busy."],
        "fix": ["Try a smaller file, a lower quality, or close other heavy programs."],
    },
    "MF-INPUT-01": {
        "title": "Please check what you entered",
        "summary": "Something in the request is not valid.",
        "what": "MediaForge could not use one of the values you entered.",
        "why": ["A link, a time or a setting is in the wrong format."],
        "fix": ["Read the message above, correct the value and try again."],
    },
    "MF-GEN-00": {
        "title": "Something went wrong",
        "summary": "MediaForge hit a problem it does not have a specific explanation for.",
        "what": "The task stopped because of an error that is not one of the common ones.",
        "why": [
            "The site changed and yt-dlp is out of date.",
            "A temporary network or disk problem.",
        ],
        "fix": [
            "Try again.",
            "Update yt-dlp from Settings.",
            "If it keeps happening, copy the technical details below when asking for help.",
        ],
    },
}


def classify(message: str) -> str:
    """Pick the error code that best matches a message. Works on raw or friendly text."""
    text = message.lower()

    def has(*words: str) -> bool:
        return any(word in text for word in words)

    if has("cookie database", "cookies from your browser") or (has("decrypt") and has("cookie")):
        return "MF-COOK-01"
    if has("not a bot", "confirm you're not a bot", "confirm you’re not a bot") or (
        has("sign in") and has("confirm")
    ):
        return "MF-SITE-01"
    if has("no video could be found", "no video formats found", "no video was found"):
        return "MF-SITE-04"
    if has(
        "getaddrinfo",
        "errno 11001",
        "name or service not known",
        "name resolution",
        "nodename nor servname",
        "failed to resolve",
        "network is unreachable",
        "could not look up",
        "could not reach that site",
    ):
        return "MF-NET-01"
    if has("connectionreset", "forcibly closed", "connection aborted", "closed the connection"):
        return "MF-NET-03"
    if has("timed out", "connect timeout", "did not answer in time"):
        return "MF-NET-02"
    if has("429", "too many requests"):
        return "MF-SITE-08"
    if has(
        "not available in your country",
        "geo restricted",
        "geo-restricted",
        "blocked in your country",
        "not made this video available",
    ):
        return "MF-SITE-07"
    if has("unsupported url"):
        return "MF-SITE-06"
    if has("403", "forbidden", "http error 401"):
        return "MF-SITE-03"
    if has(
        "private video",
        "video is private",
        "this video is private",
        "has been removed",
        "video unavailable",
        "is not available",
        "does not exist",
        "no longer available",
        "been terminated",
    ):
        return "MF-SITE-05"
    if has(
        "sign in",
        "log in",
        "login required",
        "logged in",
        "authentication",
        "age-restricted",
        "confirm your age",
        "sensitive content",
        "nsfw",
        "members-only",
        "signed in",
    ):
        return "MF-SITE-02"
    if has("live stream"):
        return "MF-LIM-01"
    if has("minute limit", "longer than the"):
        return "MF-LIM-02"
    if has("is larger than the"):
        return "MF-LIM-03"
    if has("ffmpeg was not found", "ffmpeg is not"):
        return "MF-TOOL-01"
    if has("ffmpeg could not", "could not even out"):
        return "MF-TOOL-02"
    if has("no file was produced"):
        return "MF-TOOL-03"
    if has("took too long"):
        return "MF-TOOL-04"
    return "MF-GEN-00"


def describe(code: str, technical: str | None = None) -> dict:
    """The full explanation for a code, ready to send to the page."""
    entry = CATALOG.get(code) or CATALOG["MF-GEN-00"]
    return {
        "code": code if code in CATALOG else "MF-GEN-00",
        "title": entry["title"],
        "summary": entry["summary"],
        "what": entry["what"],
        "why": list(entry["why"]),
        "fix": list(entry["fix"]),
        "technical": (technical or "")[:500] or None,
    }


def describe_exception(exc: Exception) -> dict:
    """Explain any exception. Errors raised by MediaForge carry their own code."""
    technical = getattr(exc, "technical", None) or str(exc)
    code = getattr(exc, "code", None)
    if not code:
        code = "MF-INPUT-01" if type(exc) is ValueError else classify(technical)
    return describe(code, technical)
