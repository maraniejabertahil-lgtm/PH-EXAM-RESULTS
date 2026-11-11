# SKILLS-ROUTER.md

# ChatGPT Skills Router

## 1. Purpose

This file teaches ChatGPT how to choose the best skill for a user's task.

The goal is to find the right instructions without reading every skill in the library.

## 2. Before Choosing a Skill

When the user gives a task:

1. Understand what the user wants to achieve.
2. Read `SKILLS-INDEX.md`.
3. Look for skills that match the task.
4. Check the skill descriptions and file paths.
5. Choose the most relevant skill or skills.
6. Read the complete selected `SKILL.md` files before using them.

## 3. Skill Categories

Use these categories as a guide.

### Research
Choose research skills for:
- Internet research
- Fact-checking
- Finding reliable sources
- Comparing information
- Summarizing research

### Programming
Choose programming skills for:
- Writing code
- Fixing bugs
- Building applications
- Creating websites
- Reviewing code
- Explaining programming concepts

### Writing
Choose writing skills for:
- Writing emails
- Creating articles
- Editing documents
- Writing reports
- Improving grammar
- Creating stories and content

### Business
Choose business skills for:
- Business planning
- Marketing strategies
- Business ideas
- Customer research
- Sales planning
- Business operations

### Productivity
Choose productivity skills for:
- Planning tasks
- Managing projects
- Creating workflows
- Organizing information
- Improving time management

### Data Analysis
Choose data-analysis skills for:
- Analyzing spreadsheets
- Understanding datasets
- Creating charts
- Finding patterns
- Calculating results
- Explaining data

These categories are guides, not strict limits. Always use the skill descriptions in `SKILLS-INDEX.md` to make the final choice.

## 4. Skill Selection Rules

Follow these rules:

1. Choose the skill that most closely matches the user's goal.
2. Prefer a specific skill over a general skill.
3. Use more than one skill when the task needs different types of work.
4. Do not load unrelated skills.
5. Do not choose a skill based only on its name. Check its description.
6. If two skills are equally useful, use both when appropriate.
7. If no matching skill exists, complete the task normally.

## 5. Multiple Skills

Some tasks need more than one skill.

Example:

User request: "Research a business idea and write a business proposal."

Possible skill order:

1. Research skill — find useful information.
2. Business skill — study and plan the business idea.
3. Writing skill — prepare the proposal.

Combine the instructions in a sensible order.

## 6. Missing or Unavailable Skills

If a skill is listed but its file cannot be accessed:

- Do not pretend you have read it.
- Tell the user that the skill could not be accessed.
- Continue with other available instructions when possible.

If no suitable skill exists, continue without a custom skill.

## 7. Conflict Rules

If skill instructions disagree:

1. Follow system and safety instructions first.
2. Follow the user's latest request.
3. Prefer the most specific relevant skill.
4. Combine compatible instructions.
5. Do not follow instructions that are unsafe or outside the allowed rules.

## 8. Keep the Library Organized

When new skills are added:

- Add the skill name to `SKILLS-INDEX.md`.
- Include its correct file path.
- Write a clear description of what it does.
- Put it in the correct category folder.
- Avoid creating duplicate skills unless they serve different purposes.

## 9. Final Rule

Always choose skills based on the user's actual task.

Do not load every skill for every request.

Use only the instructions that help complete the task correctly and safely.
