"""Legal safety constants (PRD §35).

Every surface that shows a verdict - UI, markdown report, PDF report, API
response - must carry the same wording: this system performs **AI-assisted
compliance screening**. It is never presented as automated legal enforcement
and never replaces a statutory inspection.

Keeping the text here (not inline in each renderer) means there is exactly
one place to amend if legal review changes the wording.
"""

SYSTEM_ROLE = "AI-assisted compliance screening"

SHORT_DISCLAIMER = (
    "AI-assisted compliance screening — not a statutory inspection."
)

DISCLAIMER = (
    "This report is produced by AI-assisted compliance screening. It is a "
    "decision-support aid for a human inspector: it highlights likely "
    "declaration issues under the Legal Metrology (Packaged Commodities) "
    "Rules, 2011 from photographs of the package. It does not constitute "
    "automated legal enforcement, does not replace statutory inspection, and "
    "carries no legal finding of contravention. Every finding must be "
    "verified by an authorised inspector before any action is taken."
)

MANUAL_VERIFICATION_NOTE = (
    "Findings marked MANUAL REVIEW could not be resolved from the captured "
    "imagery alone and require physical verification of the package."
)


def disclaimer_block(markdown: bool = True) -> str:
    """The disclaimer rendered for a text/markdown report."""
    if markdown:
        return f"> ⚖️ **{SYSTEM_ROLE.upper()}**\n>\n> {DISCLAIMER}"
    return f"{SYSTEM_ROLE.upper()}: {DISCLAIMER}"


def disclaimer_html() -> str:
    """The disclaimer rendered as an HTML banner for the frontend."""
    return (
        "<div style='border-left:4px solid #b26a00; background:#fff8e1; "
        "padding:10px 14px; border-radius:6px; margin:8px 0; "
        "font-size:0.92em; color:#4a3a10;'>"
        f"<b style='color:inherit'>⚖️ {SYSTEM_ROLE.upper()}</b><br>{DISCLAIMER}"
        "</div>"
    )
