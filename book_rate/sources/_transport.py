"""Windows curl.exe subprocess transport.

Some book platforms sit behind Cloudflare / TLS fingerprint checks that
reject python-requests; these wrappers centralize every curl invocation
so anti-bot strategy lives in exactly one place.
"""
import subprocess
import time


class CurlTransport:
    """Thin wrappers around curl.exe invocations."""

    @staticmethod
    def fetch_html(url, user_agent, headers=None, timeout=10):
        """Fetch the url via curl and return the decoded body text."""
        cmd = [
            "curl.exe", "-s", "-L", "--compressed",
            "-A", user_agent,
        ]
        for h_key, h_val in (headers or {}).items():
            if h_key.lower() not in ("user-agent", "accept-encoding"):
                cmd.extend(["-H", f"{h_key}: {h_val}"])
        cmd.append(url)
        output = subprocess.check_output(cmd, timeout=timeout)
        return output.decode("utf-8", errors="ignore")

    @staticmethod
    def probe_head(url, user_agent):
        """HEAD probe for reachability latency; returns elapsed milliseconds.

        Raises on curl failure so callers decide their own fallback text.
        """
        start_time = time.time()
        cmd = ["curl.exe", "-s", "-I", "-m", "5", "-A", user_agent, url]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
        return int((time.time() - start_time) * 1000)
