# Business Rules

Every new business module must begin from `tasks/MODULE_BRIEF_TEMPLATE.md`.
Implementation and schema work may start only when the brief is marked
`STATUS: APPROVED`, contains at least one explicitly labelled fact, has no
placeholder sections and lists `Owner decisions` as `None`.

Every governed task from TASK-164 onward must contain exactly one declaration:

```text
## Module design gate

Classification: BUSINESS_MODULE
Module identifier: <canonical_module_id>
Approved brief: tasks/module-briefs/<approved-brief>.md
```

Non-module work declares `Classification: NON_MODULE`, `Module identifier:
None`, and `Approved brief: None`. The goal-to-task planner proposal carries the
same three fields, so the runner-generated task does not need an out-of-band
content edit. `agent_runner` refuses to plan or execute a post-programme task
when this classification is missing, duplicated, identity-mismatched, unsafe,
or points to an unapproved business-module brief.

The module brief is a design gate, not an authority shortcut. Database
migrations, real-data imports, compliance decisions and external-account actions
still require their own governed task scope and owner approval.

This directory contains approved AdvanCore business rules. Rules should be written from confirmed operational facts, remain traceable to their source/approval, and distinguish configurable policy from hard system constraints.

Agents must not convert assumptions into official rules without owner approval.
