"""Generate/validate the human-readable 100-feature catalog from live code."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.feature_lab import FEATURE_GROUPS  # noqa: E402


def generate() -> str:
    count = sum(len(group) for group in FEATURE_GROUPS.values())
    if count != 100 or len(FEATURE_GROUPS) != 10 or any(len(g) != 10 for g in FEATURE_GROUPS.values()):
        raise SystemExit('Feature registry must have exactly ten groups of ten')
    if len({f.key for features in FEATURE_GROUPS.values() for f in features}) != count:
        raise SystemExit('Feature IDs must be unique')
    lines = [
        '# Floatwise V2: 100 Live Intelligence Signals',
        '',
        'These are **100 individually defined, executable calculations**, grouped into ten product areas. '
        'They are not 100 separate enterprise software modules. Each appears in the Intelligence Lab UI '
        'and is available from `GET /api/v2/features` with its ID, group, display type, definition, and live value.',
        '',
        'Calculations are transparent heuristics or deterministic aggregates. Some require the user to '
        'enter cash events, budgets, tasks, or customer profiles before they display nonzero values.',
        '',
        '| Group | Signals |', '| --- | ---: |',
    ]
    for group, features in FEATURE_GROUPS.items():
        lines.append(f'| {group} | {len(features)} |')
    lines.extend([f'| **Total** | **{count}** |', ''])
    for index, (group, features) in enumerate(FEATURE_GROUPS.items(), 1):
        lines.extend([f'## {index:02d}. {group}', '', '| ID | Feature | What it measures |', '| --- | --- | --- |'])
        for item in features:
            lines.append(f'| `{item.key}` | {item.label} | {item.description} |')
        lines.append('')
    lines.extend([
        '## Operational functionality beyond the 100 signals', '',
        '- Create, edit, list, and delete cash income/expense entries.',
        '- Maintain monthly category budgets and monitor overspending.',
        '- Manage follow-up tasks with status, priority, owner, and deadline.',
        '- Maintain customer profiles with email, segment, and payment terms.',
        '- Save and apply search views for invoices, tasks, and cash events.',
        '- Review an activity timeline, preview collection reminder drafts, and export JSON backups.',
        '- Export workspace reports as CSV or JSON and request 7–365 day forecast horizons.',
        '',
        '**Scope:** single-workspace MVP with local SQLite storage. It is not authenticated, multi-tenant, '
        'bank-connected, or intended for public deployment without additional safeguards.',
        '',
    ])
    return '\n'.join(lines)


if __name__ == '__main__':
    output = ROOT / 'FEATURES.md'
    expected = generate()
    if '--check' in sys.argv:
        if not output.exists() or output.read_text(encoding='utf-8') != expected:
            raise SystemExit('FEATURES.md is outdated. Run python -m scripts.generate_feature_catalog')
        print('Feature catalog synchronized: 100 signals')
    else:
        output.write_text(expected, encoding='utf-8')
        print(f'Generated {output} with 100 signals')

