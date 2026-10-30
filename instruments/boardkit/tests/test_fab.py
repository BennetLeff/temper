"""fab: the JLC profiles against the page they quote, the KiCad rule text and order, violation attribution.
The KiCad run itself (fab.run: self-test board + board copy) needs kicad-cli and is exercised by the boards."""
import json
import re

import pytest

from temper_boardkit import fab

PAGE = (fab.PROFILES.parent / 'jlc-capabilities-2026-10-29.txt').read_text(encoding='utf-8')
NAMES = sorted(p.stem for p in fab.PROFILES.glob('*.json'))


def test_four_jlc_profiles():
    assert NAMES == ['jlcpcb-2layer-1oz', 'jlcpcb-2layer-2oz', 'jlcpcb-4layer-1oz', 'jlcpcb-4layer-2oz']


@pytest.mark.parametrize('name', NAMES)
def test_every_limit_quoted_verbatim_from_the_page(name):
    prof = fab.profile(name)
    assert prof['schema'] == 'zapote.fab-profile.v1' and prof['name'] == name
    assert fab.validate(prof, PAGE) == []


def test_validate_catches_a_misquote():
    prof = fab.profile('jlcpcb-4layer-1oz')
    prof['limits']['minimum_pth_hole_to_copper_mm'] = 0.25
    prof['quotes']['minimum_npth_drill_mm'] = 'Min. Non-plated holes 0.40mm'
    del prof['quotes']['minimum_track_width_mm']
    problems = fab.validate(prof, PAGE)
    assert any(p.startswith('minimum_pth_hole_to_copper_mm: 0.25 not stated') for p in problems)
    assert 'minimum_npth_drill_mm: quote not in the source text' in problems
    assert 'minimum_track_width_mm: no quote' in problems


def test_stackup_differences():
    two, four = fab.profile('jlcpcb-2layer-1oz')['limits'], fab.profile('jlcpcb-4layer-1oz')['limits']
    assert (two['minimum_annular_ring_mm'], four['minimum_annular_ring_mm']) == (0.18, 0.15)
    assert (two['minimum_track_width_mm'], four['minimum_track_width_mm']) == (0.1, 0.09)
    assert 'minimum_inner_pth_hole_to_copper_mm' not in two and four['minimum_inner_pth_hole_to_copper_mm'] == 0.3
    assert fab.profile('jlcpcb-4layer-2oz')['limits']['minimum_solder_mask_web_mm'] == 0.2


def _order(rules, constraint):
    return [r['name'].replace(fab.RULE_PREFIX + ' ', '') for r in rules if r['constraint'] == constraint]


def test_rule_order_last_match_wins():
    rules = fab.rules(fab.profile('jlcpcb-4layer-1oz')['limits'])
    # general spacing before the pad rows; hole rules loosest first; via pairs after the pad hole rule
    assert _order(rules, 'clearance') == ['copper clearance', 'pad to track', 'SMD pad to pad']
    assert _order(rules, 'hole_clearance') == ['via hole to copper', 'NPTH hole to copper', 'PTH hole to copper',
                                               'inner PTH hole to copper']
    assert _order(rules, 'hole_to_hole') == ['hole to hole', 'via hole to via hole']
    # one PTH drill rule: a max rule with the same condition after a min rule would mask the min
    pth = [r for r in rules if r['name'] == f'{fab.RULE_PREFIX} PTH drill']
    assert len(pth) == 1 and '(min 0.15mm) (max 6.3mm)' in pth[0]['text']


def test_dru_text_parses_as_balanced_sexpr():
    text = fab.dru_text(fab.rules(fab.profile('jlcpcb-2layer-1oz')['limits']))
    assert text.startswith('(version 1)\n') and text.count('(') == text.count(')')
    names = re.findall(r'\(rule "([^"]+)"', text)
    assert len(names) == len(set(names)) and all(n.startswith(fab.RULE_PREFIX) for n in names)
    assert 'inner' not in text           # no inner layers on a 2-layer profile
    assert '(min 0.18mm)' in text        # the 2-layer 1 oz PTH ring


def test_attribute_by_rule_name_and_mask_type():
    rules = fab.rules({'minimum_copper_clearance_mm': 0.09, 'minimum_solder_mask_web_mm': 0.1})
    report = {'violations': [
        {'type': 'clearance', 'description': "Clearance violation (rule 'boardkit fab copper clearance' "
                                             "clearance 0.0900 mm; actual 0.0100 mm)"},
        {'type': 'clearance', 'description': "Clearance violation (netclass 'Default' clearance 0.2 mm)"},
        {'type': 'solder_mask_bridge', 'description': 'Front solder mask aperture bridges items'},
        {'type': 'via_dangling', 'description': 'Via is not connected'}]}
    got = fab.attribute(report, rules)
    assert [len(v) for v in got.values()] == [1, 1]
    assert json.dumps(got)       # serialisable
