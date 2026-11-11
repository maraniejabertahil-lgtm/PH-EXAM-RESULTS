# Humanization Skill: Multi-List Exam Detection & Routing

## Purpose
Prevent incomplete scraping runs by enabling the system to evaluate PRC announcement pages with human-like contextual awareness. Instead of naively grabbing the first list link (`lists[0]`) and exiting, this skill teaches the scraper to identify all related document links on a page, categorize them, and queue or execute them systematically.

---

## 1. Human Inspection Workflow

When a human opens a PRC licensure exam announcement, they do not just look at the top paragraph—they scan the bottom section for all official attachment links. 

The system must replicate this 4-step mental model:

1. **Scan the Footer / Attachment Links:** Look past the press release text directly to the linked attachments (e.g., "Full text", "Performance of Schools", "List of Successful Examinees...").
2. **Classify Every Link:** Differentiate between **Main Passers Lists**, **Top 10 Summaries**, and **School Performance Metrics**.
3. **Detect Sub-Categories:** Recognize when an exam is split into separate levels (e.g., *Elementary* vs. *Secondary*, *Written* vs. *Practical*, *Category A* vs. *Category B*).
4. **Queue All Target Lists:** Generate a full execution matrix for all discovered passer lists rather than stopping after the first item.

---

## 2. Link Classification Rules

| Link Pattern / Keyword | Classification | Action |
| :--- | :--- | :--- |
| `List of Successful Examinees for Elementary` | **Main List (Category 1)** | Queue for Full OCR Extraction |
| `List of Successful Examinees for Secondary` | **Main List (Category 2)** | Queue for Full OCR Extraction |
| `Roll of Successful Examinees` | **Main List (Generic)** | Queue for Full OCR Extraction |
| `Top 10` / `Garnered the Top` | **Topnotchers List** | Log / Optional Extraction |
| `Performance of Schools` | **School Summary** | Skip OCR / Store PDF Link |
| `Full Text of Official Result` | **Press Release PDF** | Skip OCR / Store PDF Link |

---

## 3. Humanized Logic Implementation Pattern

Integrate this pattern into your `article_lists()` or `prepare.py` script to make list discovery dynamic and complete.

### Python Pattern: Dynamic Multi-List Collector

```python
import re
from bs4 import BeautifulSoup

def discover_all_exam_lists(html_content):
    """
    Human-like parser: Scans the entire document to detect and categorize
    ALL pass lists present on the page.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    found_lists = []

    # Target all anchor tags across the page
    for a_tag in soup.find_all("a", href=True):
        text = re.sub(r"\s+", " ", a_tag.get_text(" ", strip=True))
        href = a_tag["href"]

        # Keyword filter matching human reading behavior for main passer lists
        if re.search(r"(list|roll) of successful", text, re.I):
            # Extract specific level/category label (e.g., "Elementary", "Secondary")
            label_match = re.search(
                r"(?:list|roll) of successful\s+\w+\s+(?:for|of)\s+(?:the\s+)?(.+)$", 
                text, 
                re.I
            )
            category_label = label_match.group(1).strip().title() if label_match else "General"

            found_lists.append({
                "label": category_label,
                "link": href,
                "text": text
            })

    return found_lists


def build_workflow_matrix(found_lists):
    """
    Humanized Queue Builder: Ensures no category is left behind.
    """
    if not found_lists:
        print("Warning: No examinee lists found on page.")
        return []

    print(f"Humanized Detector: Identified {len(found_lists)} distinct list(s):")
    for idx, item in enumerate(found_lists, 1):
        print(f"  [{idx}] Category: {item['label']} | URL: {item['link']}")

    # Returns the complete list of target jobs (e.g., both Elementary & Secondary)
    return found_lists
