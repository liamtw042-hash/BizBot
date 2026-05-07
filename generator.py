"""Generate a single-file HTML website for a business using Claude."""

import logging
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert web designer who creates clean, modern, single-file HTML websites.
When given business information, you output ONLY a complete, self-contained HTML file.
- Include all CSS inside a <style> tag in the <head>
- Use a modern, professional design with good typography
- Make it mobile-responsive using CSS flexbox/grid
- Use a tasteful color scheme appropriate for the business type
- Do NOT include any JavaScript
- Do NOT include any external resources (no CDN links, no Google Fonts URLs)
- Output ONLY the raw HTML — no markdown, no code fences, no explanation"""


def _build_prompt(business: dict) -> str:
    name = business.get("name", "Business")
    address = business.get("address", "")
    phone = business.get("phone", "")
    category = business.get("category", "business")
    city = business.get("city", "")
    rating = business.get("rating", "")

    rating_str = f" (rated {rating}/5)" if rating else ""
    return f"""Create a professional website for this local business:

Business Name: {name}
Category: {category.replace("_", " ").title()}
Location: {address or city}
Phone: {phone or "Not provided"}
Rating: {rating_str or "Not available"}

The website must include:
1. A hero section with the business name and a short tagline
2. An "About Us" section with 2-3 sentences describing the business
3. A "Services" section listing 4-6 relevant services for a {category.replace("_", " ")}
4. A "Contact" section with the address and phone number
5. A simple footer

Design requirements:
- Clean, modern look appropriate for a local {category.replace("_", " ")}
- Professional color palette
- Good readability with proper font sizing
- Fully self-contained HTML (no external dependencies)

Output ONLY the complete HTML file, starting with <!DOCTYPE html>"""


def generate_website(business: dict, config: dict) -> str:
    """Generate a website HTML string for a business using Claude."""
    api_key = config["claude_api_key"]
    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_prompt(business)

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        html = stream.get_final_message()

    # Extract text content
    content = ""
    for block in html.content:
        if block.type == "text":
            content += block.text

    # Strip any accidental markdown fences
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last fence lines
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        content = "\n".join(lines[start:end])

    if not content.strip().startswith("<!"):
        raise ValueError(f"Claude returned unexpected content for {business['name']}")

    return content


def save_website(business: dict, html: str, output_dir: str = "websites") -> str:
    """Save the HTML to disk and return the file path."""
    Path(output_dir).mkdir(exist_ok=True)

    # Sanitize business name for use as filename
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in business["name"])
    safe_name = safe_name.strip().replace(" ", "_")[:60]
    filename = f"{safe_name}.html"
    filepath = Path(output_dir) / filename

    filepath.write_text(html, encoding="utf-8")
    logger.info(f"Saved website for {business['name']} → {filepath}")
    return str(filepath)
