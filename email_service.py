"""Resend-based email sending for auth flows."""
import logging
import resend
from config import RESEND_API_KEY, RESEND_FROM, FRONTEND_URL

logger = logging.getLogger("quell.email")


def _init() -> bool:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — emails will be skipped")
        return False
    resend.api_key = RESEND_API_KEY
    return True


def _base_html(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#F4F1E9;font-family:'Inter',system-ui,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#F4F1E9;padding:48px 16px;">
  <tr>
    <td align="center">
      <table width="100%" style="max-width:520px;background:#FAF7EF;border:1px solid #DFD9CB;border-radius:16px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:#0D1009;padding:24px 32px;">
            <span style="font-family:Georgia,serif;font-size:22px;font-weight:700;color:#2D5840;letter-spacing:-0.5px;">Q</span>
            <span style="font-family:'Inter',sans-serif;font-size:16px;font-weight:600;color:#EDEAE0;margin-left:8px;letter-spacing:-0.3px;">Quell</span>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:36px 32px 32px;">
            {body}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 32px 28px;border-top:1px solid #DFD9CB;">
            <p style="margin:0;font-size:12px;color:#72756B;line-height:1.6;">
              You received this email because an action was taken on your Quell account.<br/>
              If you didn't request this, you can safely ignore this email.<br/>
              <a href="{FRONTEND_URL}" style="color:#2D5840;">quelltest.com</a>
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def send_verification_email(to_email: str, name: str, token: str) -> None:
    """Send account email-verification link."""
    if not _init():
        logger.info("DEV — verify URL: %s/auth/verify-email?token=%s", FRONTEND_URL, token)
        return

    url = f"{FRONTEND_URL}/auth/verify-email?token={token}"
    first = name.split()[0] if name else "there"

    body = f"""
<h1 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#111310;letter-spacing:-0.5px;">
  Verify your email
</h1>
<p style="margin:0 0 28px;font-size:15px;color:#4A4D44;line-height:1.65;">
  Hi {first}, click the button below to confirm your email address and
  activate your Quell account.
</p>
<a href="{url}"
   style="display:inline-block;background:#111310;color:#FAF7EF;text-decoration:none;
          font-size:14px;font-weight:600;padding:13px 28px;border-radius:10px;">
  Verify email address
</a>
<p style="margin:28px 0 0;font-size:13px;color:#72756B;line-height:1.6;">
  Or copy this link into your browser:<br/>
  <a href="{url}" style="color:#2D5840;word-break:break-all;">{url}</a>
</p>
<p style="margin:16px 0 0;font-size:12px;color:#A09E93;">
  This link expires in 24 hours.
</p>"""

    try:
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": "Verify your Quell email address",
            "html": _base_html("Verify your email — Quell", body),
        })
        logger.info("Verification email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", to_email, exc)


def send_password_reset_email(to_email: str, name: str, token: str) -> None:
    """Send password-reset link."""
    if not _init():
        logger.info("DEV — reset URL: %s/auth/reset-password?token=%s", FRONTEND_URL, token)
        return

    url = f"{FRONTEND_URL}/auth/reset-password?token={token}"
    first = name.split()[0] if name else "there"

    body = f"""
<h1 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#111310;letter-spacing:-0.5px;">
  Reset your password
</h1>
<p style="margin:0 0 28px;font-size:15px;color:#4A4D44;line-height:1.65;">
  Hi {first}, we received a request to reset your Quell password.
  Click the button below to choose a new one.
</p>
<a href="{url}"
   style="display:inline-block;background:#111310;color:#FAF7EF;text-decoration:none;
          font-size:14px;font-weight:600;padding:13px 28px;border-radius:10px;">
  Reset password
</a>
<p style="margin:28px 0 0;font-size:13px;color:#72756B;line-height:1.6;">
  Or copy this link:<br/>
  <a href="{url}" style="color:#2D5840;word-break:break-all;">{url}</a>
</p>
<p style="margin:16px 0 0;font-size:12px;color:#A09E93;">
  This link expires in 1 hour. If you didn&rsquo;t request a password reset, ignore this email.
</p>"""

    try:
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": "Reset your Quell password",
            "html": _base_html("Reset your password — Quell", body),
        })
        logger.info("Password reset email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send reset email to %s: %s", to_email, exc)
