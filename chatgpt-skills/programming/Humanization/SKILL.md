from pathlib import Path

content = r"""# Humanization Skills
## Universal PRC Examination Announcement Understanding and Complete Data Extraction

**Version:** 3.0  
**Updated:** November 11, 2026

---

## 1. Mission

Build a website system that reads Professional Regulation Commission (PRC) announcements in a careful, human-like way and extracts all relevant examination results and records.

The system must understand the whole announcement, not just the first section or list it finds. It must discover how each announcement is organized, identify every relevant result section, and extract all available records accurately.

The goal is **complete, accurate, well-organized extraction across all PRC examinations**.

## 2. Universal Coverage: All PRC Examinations

This system must support **ALL PRC examinations**, regardless of profession, specialization, examination type, or result format.

Never hardcode the system for one specific examination or profession. Do not build fixed rules that only work for Nursing, LET, Criminology, Engineering, or any other single examination.

Never assume that every announcement has:
- The same title or headings
- The same number of result lists
- The same categories or group names
- The same table columns or record fields
- The same page layout or document format
- The same way of presenting names, ratings, dates, or other details

Instead, automatically understand each announcement and adapt to the information actually present in the source.

The system should identify, when available:
- The examination or profession name
- The examination date or examination period
- The announcement or result type
- All headings, categories, groups, batches, regions, or other divisions
- Every relevant list, table, page, attachment, and continuation
- The fields and details used in that particular announcement

If an announcement contains one list, extract one list. If it contains two lists, extract both. If it contains many lists or sections, extract all of them.

**The source must guide the extraction. Do not force every source into one fixed examination structure.**

## 3. Think Like a Careful Human Reader

Follow this process for every announcement:

1. **Understand the task.** Determine what information the user wants and what kind of announcement is being read.
2. **Inspect the whole source.** Review the full webpage or document, not only the opening text or first visible list.
3. **Build a content map.** Note the headings, sections, tables, pages, links, attachments, and possible continuation points.
4. **Find every relevant section.** Look for all result lists and related information, including sections with different names.
5. **Extract each section separately.** Keep each list or group distinct and preserve its original label.
6. **Check for more content.** Review later pages, expandable areas, linked files, tables, and attachments before finishing.
7. **Verify completeness.** Compare the extracted records and sections with the source.
8. **Report honestly.** Explain what was found and clearly mark anything that could not be read or confirmed.

Never stop after finding the first matching heading, table, or list.

## 4. Detect Multiple Lists and Different Structures

An announcement may contain one or many result groups. These groups may be divided by profession, specialization, level, category, region, batch, schedule, or another label.

The system must discover these divisions from the source itself.

For example, an announcement might show separate Elementary and Secondary lists. Both must be extracted. This is only an example: other PRC announcements may use completely different categories or may have no categories at all.

Rules:
- Find every relevant list, not just the first one.
- Keep separate lists separate in the output.
- Preserve each list's actual heading or category name.
- Do not assume that category names are the same across examinations.
- Do not create a category when the source does not show one.
- Do not merge records from different groups unless the source clearly treats them as one group.
- Check whether a list continues on another page or in another file.
- Count records in each section when possible and compare those counts with the extracted data.

## 5. Read Every Supported Source Type

The information may be presented in different ways. The system should inspect all source types that are available.

### Webpages
- Read the full page, including content below the first screen.
- Inspect headings, paragraphs, tables, tabs, expandable sections, and pagination.
- Check whether more results load after scrolling or clicking a page control.
- Identify links to official result documents and related attachments.

### PDF documents
- Inspect every page, including pages after the first.
- Extract selectable text when available.
- Check tables and multi-column layouts carefully.
- Look for continuation headings and repeated table headers.
- Do not assume the document ends when the first list ends.

### Scanned documents and images
- Use OCR to read text in images or scanned pages.
- Keep the original image available for checking uncertain names or numbers.
- Mark unclear text for review instead of guessing.
- Check image-based pages as carefully as text-based pages.

### Tables
- Read all rows and columns.
- Preserve the relationship between each value and its correct heading.
- Handle tables that continue across pages.
- Do not skip rows because a table is long or split.

### Dynamic pages and attachments
- Inspect content that appears after user interaction when access is available.
- Review relevant linked official files and attachments.
- Record unavailable or inaccessible content as a limitation.
- Do not claim that the announcement is complete if important linked material could not be checked.

## 6. Flexible Data Structure

Use a flexible data model that can adapt to different examinations and result formats.

Do not require every examination to use the same fields. Some announcements may contain names and ratings; others may contain different details or only a list of names.

A useful general structure is:

- **Announcement:** source title, official source link, publication date if available, examination name if available, examination date or period if available.
- **Section:** the heading or category as written in the source, section order, and page or source location.
- **Record:** the values actually shown in that section, such as a person's name, rating, rank, number, or other available fields.
- **Provenance:** where each section and record came from, such as page number, table, or webpage section.
- **Review status:** whether the record was read clearly, needs checking, or could not be confirmed.

Field names should be based on the source. Keep original labels when useful. Do not add empty or invented fields just to make different examinations look alike.

## 7. Completeness Checks

Before marking an announcement as fully processed, check all of the following:

- [ ] The full webpage or document was reviewed.
- [ ] Every relevant heading and section was considered.
- [ ] Every relevant list and table was extracted.
- [ ] All pages were checked, including continuation pages.
- [ ] Relevant official attachments and linked result files were checked when available.
- [ ] No later list or category was skipped.
- [ ] Records remain grouped under the correct source heading.
- [ ] Unclear names or values are flagged rather than guessed.
- [ ] Extracted data was compared with the source.
- [ ] Any access or reading limits are clearly reported.

A result should be marked **complete** only when the available source has been checked and the relevant content has been accounted for.

If some pages, files, or dynamic content could not be accessed, use a status such as **partially checked**. Do not describe it as complete.

## 8. Accuracy and Source Tracking

Accuracy is just as important as completeness.

For every extracted section and record:
- Keep a link or reference to the official source.
- Keep the section heading and page or table location when possible.
- Preserve spelling, numbers, and values as shown in the source.
- Do not silently correct names or change values.
- Do not invent missing ratings, ranks, dates, categories, or records.
- Mark uncertain OCR results for review.
- Keep a record of any transformations, such as trimming extra spaces or standardizing date display.

If the source is unclear or two parts of the source disagree, show the uncertainty. Do not choose an answer without evidence.

## 9. Separate Completeness from Confidence

These are two different checks:

- **Completeness:** Did the system find and process every relevant section and record?
- **Confidence:** How sure is the system that each extracted value was read correctly?

A system may find every section but still have a few hard-to-read names. In that case, coverage may be complete while some records need review.

Show these statuses separately. Do not use a high confidence score to hide missing sections.

## 10. Recommended Processing Flow

Use a repeatable process that works for every PRC announcement:

1. Receive the official announcement URL or document.
2. Save its title, URL, and available publication details.
3. Identify the examination name and type from the source when possible.
4. Collect the full page and all relevant official documents.
5. Inspect the page and documents for their structure.
6. Detect all result sections, categories, lists, and tables.
7. Extract the records from each section.
8. Keep the source heading and location with each extracted group.
9. Run record-level checks for missing or unclear values.
10. Run section-level checks to make sure no list was missed.
11. Compare counts and content with the source where possible.
12. Save the extraction with its source and review status.
13. Show the user the results and any known limitations.

## 11. Example Pseudocode

```text
function processPRCAnnouncement(source):
    fullContent = collectAllAvailableContent(source)

    sourceMap = inspectWholeSource(fullContent)
    examDetails = identifyExamDetails(sourceMap)

    sections = discoverAllRelevantResultSections(sourceMap)
    extractedSections = []

    for section in sections:
        records = extractAllRecords(section)
        checkedRecords = verifyRecordsAgainstSource(records, section)

        extractedSections.append({
            heading: section.originalHeading,
            sourceLocation: section.location,
            records: checkedRecords,
            recordCount: count(checkedRecords)
        })

    coverage = checkAllRelevantContentAccountedFor(
        sourceMap,
        sections,
        extractedSections
    )

    return {
        examDetails: examDetails,
        sections: extractedSections,
        coverage: coverage,
        limitations: findUnreadableOrUnavailableContent(sourceMap)
    }
```

The functions above describe the required behavior. They are not tied to one profession, examination, or fixed set of categories.

## 12. AI Instructions for Reading Announcements

Use instructions like these when an AI model helps read a PRC announcement:

> Read the entire supplied PRC announcement and all available related pages or official attachments. This task applies to every PRC examination and profession. Do not assume a fixed examination type, category structure, heading, or number of result lists.
>
> First inspect the full source and identify its structure. Find every section that contains relevant examination results or records. Extract every list and table separately, keeping its original heading and order.
>
> Do not stop after the first list. Check later pages, continuation sections, tables, and relevant attachments. Adapt the output fields to the information actually shown in the source.
>
> Preserve names and values as written. Do not invent missing data or guess unclear text. Include the source location for each section when possible.
>
> Before finishing, compare the extracted sections with the full source and state whether the extraction is complete, partial, or needs review. Mention anything that could not be accessed or read.

## 13. Testing Across All PRC Examinations

Test the system with many different PRC examination announcements and layouts.

The test set should include:
- Announcements with only one result list
- Announcements with two or more result lists
- Announcements with many categories or groups
- Announcements with different headings and field names
- Long PDFs with results across many pages
- Scanned PDFs and image-based result pages
- Tables that continue across pages
- Webpages with linked official documents
- Announcements with unusual or changing layouts
- Announcements where some content is unavailable or difficult to read

Use examples from different professions and examination types. Do not let one examination become the assumed template for all others.

### Example test: two separate lists

If an announcement contains two separate lists, the system must return both lists and keep their headings.

### Example test: many pages

If a result list continues over several pages, the system must collect the records from every page.

### Example test: a new format

If an examination uses unfamiliar headings or fields, the system must adapt to the source instead of failing or forcing it into an old template.

### Example test: one list only

If the source has only one relevant list, the system must not invent extra categories.

## 14. Monitoring and Improvement

Track useful quality measures:
- Number of relevant sections found
- Number of sections successfully extracted
- Number of records extracted per section
- Number of records flagged for review
- Pages and attachments checked
- Sources that could not be accessed
- Differences found during source comparison
- Cases where a list was missed

Review failed cases and improve the general source-reading process. Avoid adding narrow rules that only fix one examination while breaking others.

## 15. Final Rules

1. Support **all PRC examinations**, not just one profession or examination.
2. Read the entire available announcement before deciding extraction is finished.
3. Discover the source's structure instead of assuming it.
4. Extract every relevant list, section, table, and continuation.
5. Keep separate categories separate and preserve their real headings.
6. Use flexible fields that match the source.
7. Check all available pages and relevant official attachments.
8. Preserve source details and show where information came from.
9. Never invent missing records or guess unclear values.
10. Report whether the result is complete, partial, or needs review.

**Most important:** The system must adapt to each PRC announcement. It must find and extract all relevant information in the source, whether there is one list, two lists, or many. No examination, profession, or result format should be excluded by a hardcoded design.
"""

path = Path("/mnt/data/Humanization_Skills.md")
path.write_text(content, encoding="utf-8")
print(f"Updated file created: {path}")
