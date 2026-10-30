"""jlc: rules and their source, EasyEDA records and fits, placement preview, order fees; kicad's pure parts."""
import json
import math

import pytest

from temper_boardkit import jlc, kicad
from temper_boardkit.jlc import easyeda, order, placement


def test_rules_quote_the_capabilities_page():
    text = jlc.capabilities_text()
    assert 'jlcpcb.com/capabilities/pcb-capabilities' in text and 'sha256' in text
    for phrase in ('Minimum Line Width ≥0.15mm', 'Minimum text height 40 mil (1.0mm)', 'ratio 1:6',
                   'Between Pad and Silkscreen is 0.15mm', 'Min. pad spacing: 0.10 mm', '0.09 mm clearance',
                   'routed board edges: ≧0.2 mm', 'V-cut board edges: ≧0.4 mm'):
        assert phrase in text, phrase
    assert jlc.RULES['edge_copper'] == 0.2 and jlc.RULES['mask_bridge'] == 0.1


def pad(num, x, y, poly=''):
    return f'PAD~RECT~{x}~{y}~4~2~1~~{num}~0~{poly}~0~gge{num}~0~~Y~0~~~~{num}'


def record(pads, head=(400, 300), model=None):
    shape = [pad(*p) for p in pads]
    if model:
        shape.append('SVGNODE~' + json.dumps({'attrs': dict(model, c_etype='outline3D')}))
    return {'packageDetail': {'title': 'TEST-2', 'dataStr': {'head': {'x': head[0], 'y': head[1]}, 'shape': shape}}}


# vendor: a 2-pad part along x, pad 1 at -x, 1.6 mm apart (6.3 canvas units ~ 1.6 mm)
VENDOR = record([('1', 396.85, 300, '394.85 299 398.85 299 398.85 301 394.85 301'), ('2', 403.15, 300)])


def test_record_cache_and_parse(tmp_path):
    (tmp_path / 'C1-product.json').write_text(json.dumps({'result': VENDOR}))
    result, sha, name = easyeda.record('C1', tmp_path)
    assert name == 'C1-product.json' and len(sha) == 64 and result == VENDOR
    with pytest.raises(FileNotFoundError):
        easyeda.record('C2', tmp_path, fetch=False)
    p = easyeda.easyeda_pads(VENDOR)
    assert p['1'] == pytest.approx((396.85 * 0.254, 300 * 0.254))
    assert easyeda.easyeda_pads(VENDOR, y_up=True)['1'][1] == pytest.approx(-300 * 0.254)
    h = easyeda.pads_about_head(VENDOR)
    assert h['1'][0] == pytest.approx((-3.15 * 0.254, 0)) and len(h['1'][1]) == 4 and h['2'][1] is None
    assert easyeda.renumber({'1': 'a', '2': 'b'}, {'1': '2', '2': '1'}) == {'2': 'a', '1': 'b'}
    assert easyeda.model_3d(record([], model={'uuid': 'u'}))['uuid'] == 'u' and easyeda.model_3d(VENDOR) is None
    assert easyeda.source_url('C1').startswith('https://lceda.cn/api/products/C1/')


def test_fit_cpl_offset_finds_the_turn():
    vendor = easyeda.easyeda_pads(VENDOR)
    native_same = {'1': (-0.8, 0.0), '2': (0.8, 0.0)}
    ranked, common = easyeda.fit_cpl_offset(native_same, vendor)
    assert ranked[0][2] == 0 and ranked[0][0] < 1e-3 and common == ['1', '2']
    native_turned = {'1': (0.0, -0.8), '2': (0.0, 0.8)}      # the footprint has the part at 90 degrees
    ranked, _ = easyeda.fit_cpl_offset(native_turned, vendor)
    assert ranked[0][0] < 1e-3 and ranked[0][2] == 270 and ranked[1][0] > 1.0
    reversed_ = {'1': (0.8, 0.0), '2': (-0.8, 0.0)}           # pad numbers swapped: 180, not 0
    assert easyeda.fit_cpl_offset(reversed_, vendor)[0][0][2] == 180


def test_fit_rigid():
    vendor = {'1': (0.0, 0.0), '2': (1.0, 0.0), '3': (0.0, 2.0)}
    native = {n: (-y + 5, x + 7) for n, (x, y) in vendor.items()}    # +90 then (5, 7)
    (rms, turn, tx, ty), *_ = easyeda.fit_rigid(native, vendor)[0]
    assert rms < 1e-9 and turn == 90 and (tx, ty) == pytest.approx((5, 7))


def test_placement_preview_pass_and_fail():
    vendor = {'C1': easyeda.pads_about_head(VENDOR)}
    board = {'R1.1': ('F_Cu', 10 - 0.8001, 20.0), 'R1.2': ('F_Cu', 10 + 0.8001, 20.0)}
    ok, outlines = placement.simulate([{'ref': 'R1', 'x': 10, 'y': 20, 'rot': 0}], {'R1': 'C1'}, vendor, board)
    assert ok['pass'] and ok['worst_mm'] < 0.01 and len(outlines) == 1 and outlines[0][1]
    bad, _ = placement.simulate([{'ref': 'R1', 'x': 10, 'y': 20, 'rot': 180}], {'R1': 'C1'}, vendor, board)
    assert not bad['pass'] and bad['worst_mm'] > 1.5
    fixed, _ = placement.simulate([{'ref': 'R1', 'x': 10, 'y': 20, 'rot': 180}], {'R1': 'C1'}, vendor, board,
                                  pin_map={'C1': {'1': '2', '2': '1'}})
    assert fixed['pass']
    svg = placement.overlay_svg((0, 0, 30, 30), [[(9, 19), (11, 19), (11, 21)]], outlines)
    assert svg.startswith('<svg') and '#ff3030' in svg


def test_read_cpl(tmp_path):
    p = tmp_path / 'cpl.csv'
    p.write_text('Designator,Mid X,Mid Y,Layer,Rotation\nR1,10.5mm,20mm,Top,90\n')
    assert placement.read_cpl(p) == [{'ref': 'R1', 'x': 10.5, 'y': 20.0, 'rot': 90.0, 'layer': 'Top'}]


def test_order_fee_model():
    assert order.tier_price([(1, 0.5), (10, 0.4), (100, 0.3)], 9) == 0.5
    assert order.tier_price([(1, 0.5), (10, 0.4), (100, 0.3)], 100) == 0.3
    assert order.buy_qty(10, 5, 20) == 20 and order.buy_qty(30, 5, 20) == 35
    assert order.is_extended('expand', False) and not order.is_extended('expand', True)
    assert order.xray_unit(10) == 1.64 and order.xray_unit(11) == 0.82
    f = order.fees(n=5, smt_parts=10.0, hand_parts=2.0, smt_joints=100, tht_joints=10, leadless=2,
                   extended_lines=3, basic_lines=4, fab=20.0)
    assert f['economic']['Extended-part fee'] == pytest.approx(9.21)
    assert f['economic']['SMT joints'] == pytest.approx(0.8) and f['economic']['X-ray'] == pytest.approx(16.4)
    assert f['standard']['Feeder loading'] == pytest.approx(3 * 3.07 + 4 * 1.53)
    rounded, totals = order.rounded(f)
    assert totals['jlc_hand_fit'] == pytest.approx(2 + 0.82 + 3.58)
    assert totals['economic'] == round(sum(f['economic'].values()), 2)
    assert order.LEADLESS.search('Package_DFN_QFN:VQFN-24') and not order.LEADLESS.search('Panasonic_TQ2SA')


def test_kicad_module_is_lazy_and_model_swap(tmp_path):
    assert kicad.MM == 1e-6          # imported without pcbnew
    name, (old, new) = next(iter(kicad.MODEL_SWAP.items()))
    (tmp_path / f'{name}.kicad_mod').write_text(f'(model "{kicad.KI3D}{old}")')
    assert kicad.apply_model_swap(tmp_path) == [name]
    assert (tmp_path / f'{name}.kicad_mod').read_text() == f'(model "{new}")'
    assert kicad.apply_model_swap(tmp_path, {'Nope': ('a', 'b')}) == []


def test_models_3d_native_pads():
    from temper_boardkit.jlc import models_3d       # importable without OCP; OCP is needed only to build
    pads = models_3d.native_pads('(pad "1" smd roundrect (at -0.825 0.5) (size 1 1))\n'
                                 '(pad "2" smd roundrect (at 0.825 0) (size 1 1))')
    assert pads == {'1': (-0.825, -0.5), '2': (0.825, 0.0)}
    assert math.isclose(models_3d.UNIT, 0.254)


def _search_reply(*codes):
    return json.dumps({'data': {'componentPageInfo': {'list': [
        {'componentCode': c, 'componentModelEn': f'M-{c}', 'componentBrandEn': 'B', 'describe': 'd',
         'componentLibraryType': 'expand', 'preferredComponentFlag': 0, 'stockCount': 100,
         'leastPatchNumber': 5, 'lossNumber': 2, 'dataManualUrl': 'u',
         'componentPrices': [{'startNumber': 1, 'productPrice': 0.5}, {'startNumber': 10, 'productPrice': 0.4}]}
        for c in codes]}}}).encode()


def test_parts_snapshot_keeps_only_the_exact_code():
    from temper_boardkit.jlc import parts
    seen = []

    def post(body):
        seen.append(json.loads(body)['keyword'])
        return _search_reply(seen[-1], seen[-1] + '9')          # the search also returns a longer code
    snap = parts.snapshot(['C2', 'C1', 'C2'], post=post, today='2026-10-29')
    assert seen == ['C1', 'C2'] and snap['fetched'] == '2026-10-29' and snap['source'] == parts.SOURCE
    assert snap['parts']['C1'] == {'model': 'M-C1', 'library': 'expand', 'preferred': False, 'stock': 100,
                                   'least': 5, 'loss': 2, 'tiers': [[1, 0.5], [10, 0.4]]}
    assert list(parts.lookup('C1', extra=True, post=lambda b: _search_reply('C1'))) == [
        'model', 'brand', 'describe', 'library', 'preferred', 'stock', 'least', 'loss', 'tiers', 'datasheet']
    with pytest.raises(AssertionError):
        parts.lookup('C3', post=lambda b: _search_reply('C1'))
