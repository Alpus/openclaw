---
name: skill-guide
description: Create or update AgentSkills. Use when designing, structuring, or packaging skills with scripts, references, and assets. Covers structure, portability, memory vs skills hierarchy, user journey-driven design, discoverability, and security.
---

# Skill Creator

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Codex's capabilities by providing
specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
domains or tasks—they transform Codex from a general-purpose agent into a specialized agent
equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. Specialized workflows - Multi-step procedures for specific domains
2. Tool integrations - Instructions for working with specific file formats or APIs
3. Domain expertise - Company-specific knowledge, schemas, business logic
4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks

## Core Principles

### Concise is Key

The context window is a public good. Skills share the context window with everything else Codex needs: system prompt, conversation history, other Skills' metadata, and the actual user request.

**Default assumption: Codex is already very smart.** Only add context Codex doesn't already have. Challenge each piece of information: "Does Codex really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

**High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.

**Medium freedom (pseudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.

**Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.

Think of Codex as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

### Portability: Skills Are Shareable, Data Is Not

**Skills must be fully portable.** You should be able to hand a skill folder to any agent or user, and it works immediately — no editing required.

**Rules:**

- **No personal data** in skill files — no names, addresses, usernames, API keys, vault names, account details, or environment-specific paths
- **No hardcoded paths** — use relative paths within the skill, or describe where the user should configure paths
- **Examples use placeholders** — `<your-username>`, `ServiceName`, `vault X` — never real values
- **User-specific data lives in the workspace**, not in the skill. The skill should explain _what_ to store and _where_ (e.g., "Store your preferences in `<workspace>/toolname/preferences.md`")

**Pattern for user data:**

```
skill-folder/           ← portable, shareable
├── SKILL.md            ← generic instructions
└── scripts/            ← generic scripts

workspace/              ← user-specific, NOT shared
├── toolname/
│   ├── preferences.md  ← user preferences
│   ├── config.md       ← user configuration
│   └── history/        ← user history/logs
```

The skill describes the _format_ and _location_ for user data. The workspace holds the actual values. This separation ensures skills can be published, shared, or installed by anyone without modification.

**Security: treat skills as public repos.** Assume any skill file may be shared or published. If personal data accidentally leaks into a skill (name, credential, path), remove it from the file AND scrub from git history (`git filter-branch` or `git filter-repo`). A simple `git rm` leaves it in history.

### Memory vs Skills: Where Knowledge Lives

Knowledge lives at three levels. Choose the right one:

**MEMORY.md** (always loaded, expensive):

- Facts needed in 90%+ of conversations (identity, preferences, key contacts)
- Critical safety rules that MUST always be present (security, boundaries)
- Brief pointers to skills: "For X, load skill Y" — one line, not details
- Never: procedures, how-tos, tool usage, domain details

**Skills** (loaded on demand, cheap):

- Procedures, workflows, tool usage, domain knowledge
- Everything that's only needed when doing a specific task
- Skills reference each other but never duplicate shared knowledge

**Workspace files** (loaded manually):

- User-specific data, history, logs, preferences
- Task tracking, daily notes

**Moving knowledge from MEMORY.md to skills:**

1. List every fact/section being moved — explicit checklist
2. Create or update the target skill with all content
3. Walk the checklist item by item — verify nothing lost
4. Final review pass — everything transferred?
5. Delete from MEMORY.md, leaving only a one-line pointer to the skill
6. Never delete before confirming the transfer is complete

**General hygiene:**

- **Before adding anything — check if it already exists.** Search MEMORY.md, relevant skills, and workspace files. Duplicate information = guaranteed divergence over time
- No duplication across files — one source of truth
- Give the fishing rod, not the fish — teach patterns, don't enumerate every case
- Concrete examples only when a case is frequent or non-obvious
- Logical sections, concise writing, only add what's not obvious from context

### User Journey-Driven Structure

When deciding how to split a skill into files, **think in user journeys**, not abstractions:

1. **List all usage scenarios** for the skill (e.g., for gym: "plan today's workout", "post-session analysis", "weekly review", "update goals")
2. **For each scenario, list what knowledge is needed** — which sections, which data
3. **Group by co-occurrence:**
   - Always needed together → keep in one file (no point splitting)
   - Needed only in specific scenarios → separate reference file
   - Rarely needed → deep reference, loaded on demand
4. **SKILL.md = the always-loaded core** — workflow overview, decision points, pointers to references
5. **References = scenario-specific details** — loaded only when that scenario is active

**Example (gym skill):**

| Scenario              | Needs                                             |
| --------------------- | ------------------------------------------------- |
| Plan workout          | philosophy, programming decisions, session format |
| Log session           | session format, exercise notation                 |
| Post-session analysis | analytics CLI, chart formatting, checklist        |
| Weekly review         | KPI definitions, goals schema, analytics CLI      |
| Update goals          | goals schema only                                 |

→ SKILL.md keeps philosophy + programming + session format (used in 3/5 scenarios). Analytics, chart rules, goals schema → `references/` (used in 1-2 scenarios each).

**The principle:** minimize total tokens loaded across all scenarios, not just file count. If splitting creates more total loading (because files are always used together), don't split.

### Discoverability: Every Path Must Be Navigable

After splitting content across files, verify that **every piece of knowledge is reachable** through a clear chain:

1. **MEMORY.md → skill**: memory mentions "for X, load skill Y" (one-line pointer)
2. **Skill description → SKILL.md**: frontmatter `description` triggers loading the skill
3. **SKILL.md → references**: each reference file is explicitly linked with **when to load it** (e.g., "Load `references/analytics.md` when doing post-session analysis")
4. **References → sub-references**: if a reference links to another file, same rule applies

**Audit checklist** (run after any restructuring):

- For every reference file: is it mentioned in SKILL.md with a clear trigger?
- For every skill: is there a path from MEMORY.md or skill description to find it?
- For every piece of knowledge: can you trace the chain from "agent wakes up" → "finds this info"?
- No orphaned files — if nothing points to it, it's invisible and useless

**Anti-pattern**: Moving content to a reference file but forgetting to add a link in SKILL.md. The content exists but is effectively lost.

### Cross-Skill References: Clear Hierarchy

When skills depend on each other, maintain a **clear separation of concerns**:

- **General-purpose skills** (e.g., browser automation, TTS, search) define _how_ a capability works — patterns, gotchas, best practices
- **Domain-specific skills** (e.g., Ocado, Gmail, GitHub) define _what_ to do on a specific site/service — URLs, page structure, workflows
- Domain skills **reference** the general skill for shared patterns, never duplicate them
- If a behavior applies to multiple sites/services, it belongs in the general skill

**Example**: "Click timeouts on SPAs are normal" → browser skill (general). "Ocado login URL is `accounts.ocado.com/...`" → Ocado skill (domain-specific).

**Pattern for referencing:**

```markdown
## Browser Automation

This skill uses **camofox-browser** for web automation. See the `camofox-browser` skill for general browser patterns (timeouts, navigation, element refs).
```

### Anatomy of a Skill

Every skill consists of a required SKILL.md file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   └── description: (required)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

Every SKILL.md consists of:

- **Frontmatter** (YAML): Contains `name` and `description` fields. These are the only fields that Codex reads to determine when the skill gets used, thus it is very important to be clear and comprehensive in describing what the skill is, and when it should be used.
- **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).

#### Bundled Resources (optional)

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Codex for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Codex's process and thinking.

- **When to include**: For documentation that Codex should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Codex determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Codex produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates, `assets/frontend-template/` for HTML/React boilerplate, `assets/font.ttf` for typography
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
- **Benefits**: Separates output resources from documentation, enables Codex to use files without loading them into context

#### What to Not Include in a Skill

A skill should only contain essential files that directly support its functionality. Do NOT create extraneous documentation or auxiliary files, including:

- README.md
- INSTALLATION_GUIDE.md
- QUICK_REFERENCE.md
- CHANGELOG.md
- etc.

The skill should only contain the information needed for an AI agent to do the job at hand. It should not contain auxiliary context about the process that went into creating it, setup and testing procedures, user-facing documentation, etc. Creating additional documentation files just adds clutter and confusion.

### Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

1. **Metadata (name + description)** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<5k words)
3. **Bundled resources** - As needed by Codex (Unlimited because scripts can be executed without reading into context window)

#### Progressive Disclosure Patterns

Keep SKILL.md body to the essentials and under 500 lines to minimize context bloat. Split content into separate files when approaching this limit. When splitting out content into other files, it is very important to reference them from SKILL.md and describe clearly when to read them, to ensure the reader of the skill knows they exist and when to use them.

**Key principle:** When a skill supports multiple variations, frameworks, or options, keep only the core workflow and selection guidance in SKILL.md. Move variant-specific details (patterns, examples, configuration) into separate reference files.

**Pattern 1: High-level guide with references**

```markdown
# PDF Processing

## Quick start

Extract text with pdfplumber:
[code example]

## Advanced features

- **Form filling**: See [FORMS.md](FORMS.md) for complete guide
- **API reference**: See [REFERENCE.md](REFERENCE.md) for all methods
- **Examples**: See [EXAMPLES.md](EXAMPLES.md) for common patterns
```

Codex loads FORMS.md, REFERENCE.md, or EXAMPLES.md only when needed.

**Pattern 2: Domain-specific organization**

For Skills with multiple domains, organize content by domain to avoid loading irrelevant context:

```
bigquery-skill/
├── SKILL.md (overview and navigation)
└── reference/
    ├── finance.md (revenue, billing metrics)
    ├── sales.md (opportunities, pipeline)
    ├── product.md (API usage, features)
    └── marketing.md (campaigns, attribution)
```

When a user asks about sales metrics, Codex only reads sales.md.

Similarly, for skills supporting multiple frameworks or variants, organize by variant:

```
cloud-deploy/
├── SKILL.md (workflow + provider selection)
└── references/
    ├── aws.md (AWS deployment patterns)
    ├── gcp.md (GCP deployment patterns)
    └── azure.md (Azure deployment patterns)
```

When the user chooses AWS, Codex only reads aws.md.

**Pattern 3: Conditional details**

Show basic content, link to advanced content:

```markdown
# DOCX Processing

## Creating documents

Use docx-js for new documents. See [DOCX-JS.md](DOCX-JS.md).

## Editing documents

For simple edits, modify the XML directly.

**For tracked changes**: See [REDLINING.md](REDLINING.md)
**For OOXML details**: See [OOXML.md](OOXML.md)
```

Codex reads REDLINING.md or OOXML.md only when the user needs those features.

**Important guidelines:**

- **Avoid deeply nested references** - Keep references one level deep from SKILL.md. All reference files should link directly from SKILL.md.
- **Structure longer reference files** - For files longer than 100 lines, include a table of contents at the top so Codex can see the full scope when previewing.

## Skill Creation Process

Skill creation involves these steps:

1. Understand the skill with concrete examples
2. Plan reusable skill contents (scripts, references, assets)
3. Initialize the skill (run init_skill.py)
4. Edit the skill (implement resources and write SKILL.md)
5. Package the skill (run package_skill.py)
6. Iterate based on real usage

Follow these steps in order, skipping only if there is a clear reason why they are not applicable.

### Skill Naming

- Use lowercase letters, digits, and hyphens only; normalize user-provided titles to hyphen-case (e.g., "Plan Mode" -> `plan-mode`).
- When generating names, generate a name under 64 characters (letters, digits, hyphens).
- Prefer short, verb-led phrases that describe the action.
- Namespace by tool when it improves clarity or triggering (e.g., `gh-address-comments`, `linear-address-issue`).
- Name the skill folder exactly after the skill name.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood. It remains valuable even when working with an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "I can imagine users asking for things like 'Remove the red-eye from this image' or 'Rotate this image'. Are there other ways you imagine this skill being used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message. Start with the most important questions and follow up as needed for better effectiveness.

Conclude this step when there is a clear sense of the functionality the skill should support.

### Step 2: Planning the Reusable Skill Contents

To turn concrete examples into an effective skill, analyze each example by:

1. Considering how to execute on the example from scratch
2. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

Example: When building a `pdf-editor` skill to handle queries like "Help me rotate this PDF," the analysis shows:

1. Rotating a PDF requires re-writing the same code each time
2. A `scripts/rotate_pdf.py` script would be helpful to store in the skill

Example: When designing a `frontend-webapp-builder` skill for queries like "Build me a todo app" or "Build me a dashboard to track my steps," the analysis shows:

1. Writing a frontend webapp requires the same boilerplate HTML/React each time
2. An `assets/hello-world/` template containing the boilerplate HTML/React project files would be helpful to store in the skill

Example: When building a `big-query` skill to handle queries like "How many users have logged in today?" the analysis shows:

1. Querying BigQuery requires re-discovering the table schemas and relationships each time
2. A `references/schema.md` file documenting the table schemas would be helpful to store in the skill

To establish the skill's contents, analyze each concrete example to create a list of the reusable resources to include: scripts, references, and assets.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, always run the `init_skill.py` script. The script conveniently generates a new template skill directory that automatically includes everything a skill requires, making the skill creation process much more efficient and reliable.

Usage:

```bash
scripts/init_skill.py <skill-name> --path <output-directory> [--resources scripts,references,assets] [--examples]
```

Examples:

```bash
scripts/init_skill.py my-skill --path skills/public
scripts/init_skill.py my-skill --path skills/public --resources scripts,references
scripts/init_skill.py my-skill --path skills/public --resources scripts --examples
```

The script:

- Creates the skill directory at the specified path
- Generates a SKILL.md template with proper frontmatter and TODO placeholders
- Optionally creates resource directories based on `--resources`
- Optionally adds example files when `--examples` is set

After initialization, customize the SKILL.md and add resources as needed. If you used `--examples`, replace or delete placeholder files.

### Step 4: Edit the Skill

When editing the (newly-generated or existing) skill, remember that the skill is being created for another instance of Codex to use. Include information that would be beneficial and non-obvious to Codex. Consider what procedural knowledge, domain-specific details, or reusable assets would help another Codex instance execute these tasks more effectively.

#### Learn Proven Design Patterns

Consult these helpful guides based on your skill's needs:

- **Multi-step processes**: See references/workflows.md for sequential workflows and conditional logic
- **Specific output formats or quality standards**: See references/output-patterns.md for template and example patterns

These files contain established best practices for effective skill design.

#### Start with Reusable Skill Contents

To begin implementation, start with the reusable resources identified above: `scripts/`, `references/`, and `assets/` files. Note that this step may require user input. For example, when implementing a `brand-guidelines` skill, the user may need to provide brand assets or templates to store in `assets/`, or documentation to store in `references/`.

Added scripts must be tested by actually running them to ensure there are no bugs and that the output matches what is expected. If there are many similar scripts, only a representative sample needs to be tested to ensure confidence that they all work while balancing time to completion.

If you used `--examples`, delete any placeholder files that are not needed for the skill. Only create resource directories that are actually required.

#### Update SKILL.md

**Writing Guidelines:** Always use imperative/infinitive form.

##### Frontmatter

Write the YAML frontmatter with `name` and `description`:

- `name`: The skill name
- `description`: This is the primary triggering mechanism for your skill, and helps Codex understand when to use the skill.
  - Include both what the Skill does and specific triggers/contexts for when to use it.
  - Include all "when to use" information here - Not in the body. The body is only loaded after triggering, so "When to Use This Skill" sections in the body are not helpful to Codex.
  - Example description for a `docx` skill: "Comprehensive document creation, editing, and analysis with support for tracked changes, comments, formatting preservation, and text extraction. Use when Codex needs to work with professional documents (.docx files) for: (1) Creating new documents, (2) Modifying or editing content, (3) Working with tracked changes, (4) Adding comments, or any other document tasks"

Do not include any other fields in YAML frontmatter.

##### Body

Write instructions for using the skill and its bundled resources.

### Step 5: Packaging a Skill

Once development of the skill is complete, it must be packaged into a distributable .skill file that gets shared with the user. The packaging process automatically validates the skill first to ensure it meets all requirements:

```bash
scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory specification:

```bash
scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Validate** the skill automatically, checking:
   - YAML frontmatter format and required fields
   - Skill naming conventions and directory structure
   - Description completeness and quality
   - File organization and resource references

2. **Package** the skill if validation passes, creating a .skill file named after the skill (e.g., `my-skill.skill`) that includes all files and maintains the proper directory structure for distribution. The .skill file is a zip file with a .skill extension.

   Security restriction: symlinks are rejected and packaging fails when any symlink is present.

If validation fails, the script will report the errors and exit without creating a package. Fix any validation errors and run the packaging command again.

### Step 5.5: Post-Edit Verification (MANDATORY)

After ANY skill edit (creation, restructuring, splitting, moving content):

1. **Commit all changes**: `git add -A && git commit`
2. **Review the full diff**: `git diff HEAD~1` (or against the last clean state)
3. **Walk the diff line by line**: for every deleted line, verify it exists elsewhere (new file, reference, etc.)
4. **Check discoverability**: every reference file linked in SKILL.md? Every skill reachable from MEMORY.md or frontmatter?
5. **No orphaned content**: if something was moved, the source must have a pointer to the destination

This is not optional. Content silently lost during restructuring is the #1 failure mode.

### Step 6: Iterate

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Iteration workflow:**

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again
