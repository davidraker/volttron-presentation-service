"""Rename the ``61850`` hub's keys to IEC 61850-7-420 Edition 2 names (sources plan step 4).

    python tools/hub_edition2_rename.py [--apply] [--transforms DIR]

Without ``--apply`` the script reports what it would change. The table below is the record of the rename: group
renames (instance numbers dropped or kept as documented instances, profile inventions moved to ``x-`` extension
groups), data-object renames (generic Edition 1 and MESA names to their Edition 2 objects, or to ``x-`` extension
objects where Edition 2 has none), moves between classes, nested path rewrites (meters out of DECP, ride-through
curves onto PTOV/PTUV/PTOF/PTUF instances) and deletions (DNP3 curve-store mechanics). HUB_61850_FORMAT.md §2
documents the resulting conventions; tests/test_hub_vocabulary.py checks the result against the NSD files.

Both sides of a hub edge are rewritten: the pattern keys of ``*_to_61850`` edges and the source segments of
``transform[...]`` expressions in ``61850_to_*`` edges, including relative references inside schedule entries.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

HUB = '61850'
DELETE = object()

# ---- groups: old hub group -> new group path (tuple) or DELETE. Unlisted groups keep their name.
GROUPS: dict[str, tuple | object] = {
    'DHFW1': ('DHFW',), 'DHFW2': ('DHFW2',), 'DLFW1': ('DLFW',), 'DLFW2': ('DLFW2',),
    'DCTE1': ('DCTE',), 'DCTE2': ('DCTE',), 'DCTE3': ('DCTE',),
    'DWFL1': ('DWFL',), 'DWFL2': ('DWFL2',), 'DWFL3': ('DWFL3',),
    'DECP1': ('x-MESA',), 'DECPn': ('x-MESA',),
    'DVWD': ('x-DVWD',), 'DVWD 2': ('x-DVWD',), 'DWSM': ('x-DWSM',), 'DPFC': ('x-DPFC',), 'DPRG': ('x-DPRG',),
    'DVVC': ('DVVR',), 'DFWC': ('DHFW2',),
    'MESA': ('x-MESA',), 'MESAn': ('x-MESA',), 'FSCCn': ('x-MESA',), 'FSCHn': ('x-MESA', 'SelSchd'),
    'DGSMn': DELETE, 'FMARn': DELETE,
    'MMXU1': ('MMXU',), **{f'MMXU{i}': DELETE for i in range(2, 12)}, **{f'MMXN{i}': DELETE for i in range(2, 6)},
}
# per old group: data-object renames applied before the generic table
GROUP_DO: dict[str, dict[str, str]] = {
    'DCTE2': {'WinTms': 'x-CeaWinTms', 'RmpTms': 'x-CeaRmpTms', 'RvrtTms': 'x-CeaRvrtTms'},
    'DECP1': {'EcpIsldSt': 'ReqSetGrp'}, 'DECPn': {'EcpIsldSt': 'EditSetGrp'},
    'MESAn': {'SchdTyp': 'SelSchdTyp'}, 'FSCCn': {'Schd': 'SelSchdId'},
    'DCTE1': {'WinTms': 'x-RtnRndTmms'},     # the profile's return-to-service "time window" is its randomisation window
    'DWMX': {'LimW': 'WMaxSpt'}, 'DWMN': {'LimW': 'WMinSpt'},
    'DVVR': {'VRef': 'VRefSpt', 'VRefSet': 'VRefEsp'},
    'DFPF': {'PFExtSet': 'PFGnExtQud'},
    'PTOV1': {'BlkRef': 'x-CrvRef'}, 'PTOV2': {'BlkRef': 'x-CrvRef'}, 'PTUV1': {'BlkRef': 'x-CrvRef'}, 'PTUV2': {'BlkRef': 'x-CrvRef'},
    'PTOF1': {'BlkRef': 'x-CrvRef'}, 'PTOF2': {'BlkRef': 'x-CrvRef'}, 'PTUF1': {'BlkRef': 'x-CrvRef'}, 'PTUF2': {'BlkRef': 'x-CrvRef'},
    'CSWI': {'Pos.1': 'Pos', 'Pos.2': 'x-PosMoving'},     # BI23 switch closed -> Pos (DPC: 1 open, 2 closed); BI24 moving
    'DHFW': {'WMax': 'x-WMax', 'WMin': 'x-WMin'}, 'DLFW': {'WMax': 'x-WMax', 'WMin': 'x-WMin'},
    'DHFW1': {'WMax': 'x-WMax', 'WMin': 'x-WMin'}, 'DLFW1': {'WMax': 'x-WMax', 'WMin': 'x-WMin'},
}
# generic data-object renames (Edition 1 / MESA name -> Edition 2 object, or x- extension object)
DO: dict[str, str] = {
    'ModEna': 'Mod', 'EcpRef': 'InEcpRef', 'OpnLoopMax': 'OplTmsMax', 'UseRmpRte': 'RmpRteUse',
    'RpuRte': 'RpuMax', 'RpdRte': 'RpdMax', 'RpuChaRte': 'ChaRpuMax', 'RpdChaRte': 'ChaRpdMax',
    'ChaRpuRte': 'ChaRpuMax', 'ChaRpdRte': 'ChaRpdMax', 'DschRpuRte': 'RpuMax', 'DschRpdRte': 'RpdMax',
    'RpuRteMax': 'RpuMax', 'RpdRteMax': 'RpdMax', 'RpuChaRteMax': 'ChaRpuMax', 'RpdChaRteMax': 'ChaRpdMax',
    # the profile's "ramp up time constant" is the open-loop response time every other protocol carries once;
    # the "ramp down" constant has no Edition 2 object
    'RmpUpTms': 'OplTmsMax', 'RmpDnTms': 'x-RmpDnTms', 'OplTmsMax[1]': 'OplTmsMax', 'OplTmsMax[2]': 'x-RmpDnTms',
    'SnptEna': 'SnptBarEna', 'ActStrDlTmms': 'StrDlTmms', 'ActStopDlTmms': 'StopDlTmms',
    'ReqWLim': 'ReqW', 'ReqWSet': 'ReqW', 'WChaGra': 'ChaWGra', 'HysCrv': 'x-HysCrvRef',
    'SocUseMax': 'SocUseMaxPct', 'SocUseMin': 'SocUseMinPct', 'VArTgt': 'VArTgtSpt', 'GnWPctSpt': 'WSptPct',
    'PFGnTgt': 'PFGnTgtSpt', 'PFLodTgt': 'PFLodTgtSpt', 'PFGnExtSet': 'PFGnExtQud', 'PFLodExtSet': 'PFLodExtQud',
    'RtnSrvAuth': 'RtnSvcAuth', 'RtnSrvDlyTim': 'RtnDlTmms', 'RtnDlyTmms': 'RtnDlTmms', 'RtnSrvRmpTim': 'RtnRmpTmms',
    'RtnSrvRndTim': 'x-RtnRndTmms', 'DERState': 'DEROpSt', 'Ieee1547Cat1': 'x-Ieee1547CatNorm', 'Ieee1547Cat2': 'x-Ieee1547CatAbn',
    'RegClas[1]': 'x-Ieee1547CatNorm', 'RegClas[2]': 'x-Ieee1547CatAbn', 'RegCap': 'x-RegCap', 'EmgStop': 'x-EmgStop',
    'OpnLoopTau': 'x-OplTauMod', 'PrmConn': 'AuthConn', 'PrmDscon': 'AuthDscon', 'VArRef': 'VArSptRef', 'VArSetRef': 'VArSptRef',
    'VarMaxAbgRtg': 'IvarMaxRtg', 'VarMaxSupRtg': 'AvarMaxRtg', 'Vmax': 'VMax', 'Vmin': 'VMin',
    'WGnOvPFRtg': 'WOvPFRtg', 'WGnUnPFRtg': 'WUnPFRtg', 'SocPct': 'x-SocPct', 'SocUsePct': 'UseSocPct', 'SoH': 'x-SoH',
    'AGra': 'x-CapUnit', 'VAChaMax': 'ChaVAMax', 'VAMaxChaRtg': 'ChaVAMaxRtg', 'WChaMax': 'ChaWMax',
    # every edge but 1815.2 used the under-excited name for the plain maximum charging rating (AI5 = ChaWMaxRtg)
    'WChaUnPFRtg': 'ChaWMaxRtg',
    'VADisChaRteMaxRtg': 'DschVAMaxRtg', 'WDisChaRteMaxRtg': 'DschWMaxRtg', 'WhAvail': 'SocWh',
    'ECPIsldAuto': 'EcpIsldAuto', 'EcpConnType': 'x-EcpConnTyp', 'EcpNomHz': 'HzNom',
    'ChaDurTms': 'x-ChaDurMin', 'SocDateTms': 'DateTgt', 'DateTgt[Date]': 'x-DateTgtDate', 'DateTgt[Time]': 'x-DateTgtTime',
    'HoldTmms[1]': 'x-StrHoldTmms', 'HoldTmms[2]': 'HoldTmms', 'TmVCrv': 'TmVChr', 'TmHzCrv': 'x-TmHzChr', 'SchdEntr': 'x-SchdEntr',
}
# (group, data object) -> (new group, new data object): objects that live on another class in Edition 2
MOVES: dict[tuple[str, str], tuple[str, str]] = {
    ('DECP', 'VRefOfs'): ('DVVR', 'VRefOfs'), ('DGEN', 'GriMod'): ('DINV', 'GriMod'), ('DSTO', 'GriMod'): ('DINV', 'GriMod'),
    ('DSTO', 'Stdby'): ('DINV', 'Stdby'), ('DSTO', 'BatSt'): ('DBAT', 'BatSt'),
    ('DBAT', 'ExtTmpHiAlm'): ('SBAT', 'ExtTmpHiAlm'), ('DBAT', 'IntnTmpHiAlm'): ('SBAT', 'IntnTmpHiAlm'),
    ('DCTE', 'RpuRteMax'): ('DGEN', 'WRpuMaxRtg'), ('DCTE', 'RpdRteMax'): ('DGEN', 'WRpdMaxRtg'),
    ('DCTE', 'RpuChaRteMax'): ('DSTO', 'x-ChaWRpuMaxRtg'), ('DCTE', 'RpdChaRteMax'): ('DSTO', 'x-ChaWRpdMaxRtg'),
    ('MMXU1', 'TotChaW'): ('DSTO', 'AvlChaW'), ('MMXU1', 'TotW'): ('DSTO', 'AvlDschW'),
    ('DSTO', 'InclDER'): ('x-MESA', 'NumDER'),
}
# nested path prefixes rewritten as a whole (old segments -> new segments)
PATHS: dict[tuple, tuple] = {
    ('DECP', 'MMXU'): ('MMXU',),
    ('DHVT', 'TrZnSt', 'PTOV'): ('PTOV1',), ('DHVT', 'CeaZnSt', 'PTOV'): ('PTOV2',),
    ('DLVT', 'TrZnSt', 'PTUV'): ('PTUV1',), ('DLVT', 'CeaZnSt', 'PTUV'): ('PTUV2',),
    ('DHFT', 'TrZnSt', 'PTOF'): ('PTOF1',), ('DHFT', 'CeaZnSt', 'PTOF'): ('PTOF2',),
    ('DLFT', 'TrZnSt', 'PTUF'): ('PTUF1',), ('DLFT', 'CeaZnSt', 'PTUF'): ('PTUF2',),
}
# enumeration and double-point objects whose bits or labels the hub used as keys: the bits become an x- object
BIT_OBJECTS = {'DEROpSt', 'CeaEgzReqCtl', 'CeaEgzReqSt', 'DERState'}
# attribute renames inside measured values
ATTRS = {'range': 'rangeC'}

# per transform file (substring of the file name): group and data-object renames that differ from the tables above
FILE_OVERRIDES = {
    '1815.2': {'groups': {'DHFW': ('DHFW2',), 'DLFW': ('DLFW2',)}, 'do': {'WChaUnPFRtg': 'ChaWUnPFRtg'}},   # AI10 really is the under-excited rating      # the profile's unnumbered DHFW is its curve variant
    'rtc_controller': {'groups': {}, 'do': {'SocUsePct': 'x-SocUsePct'}},   # the RTC format carries usable SoC twice; UseSocPct is the Edition 2 one
}
_ACTIVE = {'groups': {}, 'do': {}}

LN_LIKE = re.compile(r'^(x-)?[A-Z][A-Za-z0-9]{3,}( \d+|n)?$')


def _split_suffix(seg: str) -> tuple[str, str]:
    m = re.match(r'^([^\[]+)(\[.*\])?$', seg)
    return (m.group(1), m.group(2) or '') if m else (seg, '')


def _is_group(seg: str) -> bool:
    return bool(LN_LIKE.match(seg)) and not seg.startswith('x-') or seg in GROUPS or seg.startswith('x-')


def rename_path(segments: list[str], changes: list) -> list[str] | None:
    """Rewrite one hub path (a pattern key chain, or the segments of a hub-side transform reference).

    Returns the new segments, or None when the path is deleted. Segments after a schedule entry marker are LN groups
    again and are rewritten recursively."""
    if not segments:
        return segments
    segs = list(segments)
    for old, new in PATHS.items():
        if tuple(segs[:len(old)]) == old:
            segs = list(new) + segs[len(old):]
            changes.append(('path', '.'.join(old), '.'.join(new)))
            break
    group = segs[0]
    target = _ACTIVE['groups'].get(group, GROUPS.get(group))
    if target is DELETE:
        changes.append(('delete', group, ''))
        return None
    new_group = list(target) if target else [group]
    out = new_group
    rest = segs[1:]
    if not rest:
        return out
    do = rest[0]
    do_rest = rest[1:]
    # two-segment keys like 'Pos.1' arrive as separate segments; look them up joined first
    joined = f'{do}.{do_rest[0]}' if do_rest else None
    g_table = GROUP_DO.get(group, {})
    if joined and joined in g_table:
        do, do_rest = g_table[joined], do_rest[1:]
    elif do in g_table:
        do = g_table[do]
    elif (group, do) in MOVES or (new_group[0], do) in MOVES:
        ng, nd = MOVES.get((group, do)) or MOVES[(new_group[0], do)]
        changes.append(('move', f'{group}.{do}', f'{ng}.{nd}'))
        out, do = [ng], nd
    elif do in _ACTIVE['do']:
        do = _ACTIVE['do'][do]
    elif do in DO:
        do = DO[do]
    elif _split_suffix(do)[0] in DO:          # 'SchdEntr[#]' renames like 'SchdEntr', keeping its index
        do = DO[_split_suffix(do)[0]] + _split_suffix(do)[1]
    # bit or label used as a key under an enumeration: the bits become an extension object
    bare = re.sub(r'\[.*\]$', '', do)
    if bare in BIT_OBJECTS and do_rest and (do_rest[0].isdigit() or do_rest[0][:1].islower()):
        do = f'x-{bare}Bits'
    elif bare in BIT_OBJECTS and do != 'DEROpSt':
        do = 'DEROpSt' if bare == 'DERState' else do
    out = out + [do]
    # nested content: schedule entries hold LN groups again
    if bare in ('x-SchdEntr', 'SchdEntr'):
        i = 0
        while i < len(do_rest) and (do_rest[i] in ('#', '*') or do_rest[i].startswith('[')):
            out.append(do_rest[i]); i += 1
        inner = do_rest[i:]
        if inner and inner[0] in ('StrTm', 'SchdIntv', '#'):
            return out + inner
        if inner:
            nested = rename_path(inner, changes)
            return None if nested is None else out + nested
        return out
    # attribute level: curve names, range -> rangeC
    for seg in do_rest:
        s = DO.get(seg, seg) if seg in ('TmVCrv', 'TmHzCrv') else ATTRS.get(seg, seg)
        out.append(s)
    return out


def rename_pattern(pattern: dict, changes: list) -> dict:
    """Rewrite the hub-side keys of an output=61850 pattern, merging groups that become one."""
    flat: list[tuple[list[str], object]] = []

    def walk(node, prefix):
        if isinstance(node, dict):
            for k, v in node.items():        # an empty group contributes nothing
                walk(v, prefix + [k])
        else:
            flat.append((prefix, node))

    walk(pattern, [])
    out: OrderedDict = OrderedDict()
    for path, value in flat:
        # keys may contain dots that mean nesting of enumeration bits ('Pos.1'); split them for the renamer
        segs = []
        for k in path:
            segs += k.split('.') if re.match(r'^[A-Za-z]+\.(\d+|[a-z][a-z ]*)$', k) else [k]
        new = rename_path(segs, changes)
        if new is None:
            continue
        if new != segs:
            changes.append(('key', '.'.join(segs), '.'.join(new)))
        node = out
        for k in new[:-1]:
            node = node.setdefault(k, OrderedDict())
            if not isinstance(node, dict):
                raise SystemExit(f'conflict: {".".join(new)} descends through a leaf')
        if new[-1] in node and node[new[-1]] != value:
            changes.append(('CONFLICT', '.'.join(new), f'{node[new[-1]]!r} vs {value!r}'))
        node[new[-1]] = value
    return out


REF = re.compile(r'transform\[((?:[^\[\]]|\[[^\]]*\])*)\]')    # one level of inner brackets: Name[#], Name[1]


def rename_references(text: str, changes: list, context_groups: set[str]) -> str:
    """Rewrite hub-side source references in an input=61850 edge's pattern text."""
    def fix(m):
        raw = [s.strip() for s in m.group(1).split(',')]
        quoted = [s[:1] in ("'", '"') or s.startswith('\\"') for s in raw]
        segs = [s.strip('\'').replace('\\"', '') for s in raw]      # the files quote segments with ' or \"
        if not segs or not segs[0]:
            changes.append(('delete-ref', '(empty)', ''))
            return DELETED_REF
        if segs[0] == '#':
            # relative to a list element: inside a schedule entry the next segment is an LN group
            if len(segs) > 1 and (segs[1] in GROUPS or LN_LIKE.match(segs[1])) and segs[1] not in ('StrTm', 'SchdIntv'):
                new = rename_path(segs[1:], changes)
                return DELETED_REF if new is None else 'transform[' + ', '.join(['#'] + [_quote(x) for x in new]) + ']'
            return m.group(0)
        if segs[0] in GROUPS or LN_LIKE.match(segs[0]) or segs[0] in context_groups:
            new = rename_path(segs, changes)
            if new is None:
                changes.append(('delete-ref', ', '.join(segs), ''))
                return DELETED_REF
            if new != segs:
                changes.append(('ref', ', '.join(segs), ', '.join(new)))
            return 'transform[' + ', '.join(_quote(s) for s in new) + ']'
        return m.group(0)
    return REF.sub(fix, text)


DELETED_REF = 'transform[__deleted__]'


def drop_deleted(node):
    """Remove pattern keys whose expression read a deleted hub group (the DNP3 curve-store mechanics)."""
    if isinstance(node, dict):
        for k in [k for k, v in node.items() if isinstance(v, str) and DELETED_REF in v]:
            del node[k]
        for v in node.values():
            drop_deleted(v)
    return node


def _quote(seg: str) -> str:
    """Segments with a hyphen (the x- extensions) are quoted in a transform reference, with single quotes as the
    files already do for other segments; the grammar accepts quoted segments."""
    seg = seg.strip()
    needs = '-' in seg or ' ' in seg or ('[' in seg and not seg.endswith('[#]'))   # literal keys like SchdSt[1], StrTm[Date]
    return f"'{seg}'" if needs and not seg.startswith("'") else seg


def _relative_refs(node, out):
    """Every ``transform[#, ...]`` reference in a group, not descending into nested explicit-root groups."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k != '#':
                _relative_refs(v, out)
    elif isinstance(node, str):
        for m in REF.finditer(node):
            segs = [s.strip().strip("'") for s in m.group(1).split(',')]
            if segs[:1] == ['#'] and len(segs) > 1:
                out.append(segs)


def _root_segments(root: str) -> list[str]:
    m = REF.search(root)
    return [s.strip().strip("'") for s in m.group(1).split(',')] if m and m.group(1).strip() else []


def rename_input_pattern(node, changes: list, stack: list | None = None):
    """Rewrite the hub-side references of an input=61850 pattern.

    ``stack`` holds, for each enclosing list element, ``(resolve, base)``: the element's hub path in old names, used
    to resolve ``transform[#, ...]`` references, and the old path of what ``#`` denotes when the group was rebased on
    its enclosing element. A group is rebased (``"#": "transform(as_list())"``, which the grammar allows) when the
    rename moves one of its paths out of the element, as the ride-through curves leave DHVT for PTOV1/PTOV2."""
    stack = stack or []
    if isinstance(node, dict):
        root = node.get('#')
        new_stack = stack
        if isinstance(root, str):
            segs = _root_segments(root)
            parent_resolve, parent_base = stack[-1] if stack else ([], [])
            if segs and segs[0] == '#':
                element = parent_resolve + segs[1:]
            elif segs:
                element = segs
            else:
                element = parent_resolve
            if segs and (segs[0] == '#' or segs[0] in GROUPS or LN_LIKE.match(segs[0])):
                renamed_element = rename_path(element, []) or []
                refs: list = []
                _relative_refs(node, refs)
                moved = any(r[1] not in ('StrTm', 'SchdIntv') and (lambda f: f is not None and f[:len(renamed_element)] != renamed_element)(rename_path(element + r[1:], [])) for r in refs)
                node = OrderedDict(node)
                if moved:
                    node['#'] = REF.sub('transform', root, count=1)
                    changes.append(('rebase', '.'.join(element), '.'.join(parent_base) or 'message'))
                    base = parent_base
                elif segs[0] == '#':
                    rel = rename_path(element, []); parent_new = rename_path(parent_base, []) if parent_base else []
                    if rel is not None and rel[:len(parent_new)] == parent_new:
                        node['#'] = REF.sub('transform[' + ', '.join(['#'] + [_quote(s) for s in rel[len(parent_new):]]) + ']', root, count=1)
                    base = element
                else:
                    new_root = rename_path(element, changes)
                    if new_root is not None:
                        node['#'] = REF.sub('transform[' + ', '.join(_quote(s) for s in new_root) + ']', root, count=1)
                    base = element
                new_stack = stack + [(element, base)]
        out = OrderedDict()
        for k, v in node.items():
            if k == '#':
                out[k] = v
                continue
            new_v = rename_input_pattern(v, changes, new_stack)
            if isinstance(new_v, str) and DELETED_REF in new_v:
                continue
            out[k] = new_v
        return out
    if isinstance(node, list):
        return [rename_input_pattern(v, changes, stack) for v in node]
    if isinstance(node, str):
        if stack:
            resolve, base = stack[-1]
            new_base = rename_path(base, []) or [] if base else []
            def fix(m):
                segs = [s.strip().strip("'") for s in m.group(1).split(',')]
                if segs[:1] != ['#'] or len(segs) < 2 or segs[1] in ('StrTm', 'SchdIntv'):
                    return m.group(0)
                full = rename_path(resolve + segs[1:], changes)
                if full is None:
                    return DELETED_REF
                tail = full[len(new_base):] if full[:len(new_base)] == new_base else full
                return 'transform[' + ', '.join(['#'] + [_quote(s) for s in tail]) + ']'
            node = REF.sub(fix, node)
        return rename_references(node, changes, set())
    return node


# ---- semantic corrections to the 1815.2 hub edges, found by the route-consistency test once the names unified
# (tests/test_graph_invariants.py): the profile's AI12/AI34/AI45 are reactive *injection* (AvarMaxRtg/AvarMax/AvarAvl) and
# AI13/AI35/AI46 *absorption* (Ivar...), the edges had them swapped; and BI29/BI30 (BO10/BO11) are 0 = injecting VArs,
# so the hub's PFGnExtQud/PFLodExtQud (true = over-excited, injecting) is equals(0) of the point, not a copy.
SWAP = [('IvarMaxRtg', 'AvarMaxRtg'), ('IvarMax', 'AvarMax'), ('IvarAvl', 'AvarAvl')]
EXCITATION = {'PFGnExtQud', 'PFLodExtQud'}


def fix_1815_2(edge, changes: list):
    import re as _re
    if edge.get('output_format') == HUB:
        def walk(node):
            if not isinstance(node, dict):
                return
            if 'Pos' in node and isinstance(node['Pos'], str) and node['Pos'].endswith(']()') and 'B' in node['Pos']:
                node['Pos'] = node['Pos'][:-2] + '(select(2, 1))'      # closed -> 2, open -> 1 (DPC stVal)
                changes.append(('switch', 'Pos', node['Pos']))
            for a, b in SWAP:
                if a in node and b in node:
                    node[a], node[b] = node[b], node[a]
                    changes.append(('swap', a, b))
            for k, v in node.items():
                if k in EXCITATION and isinstance(v, str) and v.endswith('()'):
                    node[k] = v[:-2] + '(equals(0))'
                    changes.append(('invert', k, v))
                walk(v)
        walk(edge['pattern'])
    elif edge.get('input_format') == HUB:
        def walk(node):
            if not isinstance(node, dict):
                return
            for k, v in list(node.items()):
                if isinstance(v, str):
                    for a, b in SWAP:
                        if _re.search(rf'transform\[DGEN, {a}\]', v):
                            node[k] = v.replace(f'[DGEN, {a}]', f'[DGEN, {b}]'); changes.append(('swap-ref', a, b))
                        elif _re.search(rf'transform\[DGEN, {b}\]', v):
                            node[k] = v.replace(f'[DGEN, {b}]', f'[DGEN, {a}]'); changes.append(('swap-ref', b, a))
                    v = node[k]
                    # AI38/AI39 (minimum and maximum voltage settings) are DGEN.VMin/VMax, as the writer edge and
                    # every other protocol have them; the reader pointed at the connection point's ratings
                    if k in ('38', '39') and v in ('transform[DECP, VMin]()', 'transform[DECP, VMax]()'):
                        node[k] = v.replace('DECP', 'DGEN'); changes.append(('fix-ref', k, v)); v = node[k]
                    if v == 'transform[CSWI, Pos]()' and k in ('23', '5'):
                        node[k] = 'transform[CSWI, Pos](equals(2))'; changes.append(('switch-ref', k, v)); v = node[k]
                    if any(f'[DFPF, {e}]()' in v for e in EXCITATION):
                        node[k] = v[:-2] + '(select(0, 1), cast_value(bool))'; changes.append(('invert-ref', k, v))
                else:
                    walk(v)
        walk(edge['pattern'])


def fix_connection_status(edge, changes: list):
    """The connected/disconnected status every protocol carries (SunSpec 701.ConnSt, 2030.5 connectStatus, the 1547
    Connection Status, 1815.2 BI23) is the connect/disconnect switch, CSWI.Pos (DPC: 1 open, 2 closed), not bit 1 of a
    DER state enumeration. Writers set Pos with select(2, 1); readers test equals(2)."""
    pattern = edge['pattern']
    if edge.get('output_format') == HUB:
        for group in list(pattern):
            node = pattern[group]
            bits = node.get('x-DEROpStBits') if isinstance(node, dict) else None
            if isinstance(bits, dict) and isinstance(bits.get('1'), str):
                expr = bits.pop('1')
                # the source's own encoding first: SunSpec ConnSt is an enumeration (1 = connected), the 2030.5
                # connectStatus a bit field (bit 0 = connected), the others booleans
                flag = '(equals(1), select(2, 1))' if '701, ConnSt' in expr else '(bit(0), select(2, 1))' if 'connectStatus' in expr else '(select(2, 1))'
                pattern.setdefault('CSWI', OrderedDict())['Pos'] = expr[:-2] + flag if expr.endswith('()') else expr
                changes.append(('switch', f'{group}.x-DEROpStBits.1', 'CSWI.Pos'))
                if not bits:
                    del node['x-DEROpStBits']
    elif edge.get('input_format') == HUB:
        def walk(node):
            if isinstance(node, dict):
                for k, v in list(node.items()):
                    if isinstance(v, str) and "'x-DEROpStBits', 1]()" in v:
                        node[k] = 'transform[CSWI, Pos](equals(2), select(1, 0))' if k in ('ConnSt', 'connectStatus') else 'transform[CSWI, Pos](equals(2))'
                        changes.append(('switch-ref', k, v))
                    else:
                        walk(v)
        walk(pattern)


# The direct (non-hub) edges copied the 2030.5 connectStatus bit field straight into booleans and enumerations; the
# route-consistency test shows it once the hub carries the switch position. Same encodings as fix_connection_status.
DIRECT_CONNECTION_STATUS = {
    '2030.5_to_1547.json': ('transform[DERStatus, connectStatus]()', 'transform[DERStatus, connectStatus](bit(0))', 'Connection Status'),
    '1547_to_2030.5.json': ("transform[Monitoring, 'Connection Status']()", "transform[Monitoring, 'Connection Status'](select(1, 0))", 'connectStatus'),
    '2030.5_to_sunspec.json': ('transform[DERStatus, connectStatus]()', 'transform[DERStatus, connectStatus](bit(0), select(1, 0))', 'ConnSt'),
    'sunspec_to_2030.5.json': ('transform[701, ConnSt]()', 'transform[701, ConnSt](equals(1), select(1, 0))', 'connectStatus'),
    '2030.5_to_1815.2.json': ('transform[DERStatus, connectStatus]()', 'transform[DERStatus, connectStatus](bit(0))', '23'),
    '1815.2_to_2030.5.json': ('transform[BI, 23]()', 'transform[BI, 23](select(1, 0))', 'connectStatus'),
}


def fix_direct_connection_status(path: Path, apply: bool) -> list:
    old, new, key = DIRECT_CONNECTION_STATUS[path.name]
    edges = json.loads(path.read_text(), object_pairs_hook=OrderedDict)
    changes = []
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key and v == old:
                    node[k] = new
                    changes.append(('direct-switch', path.name, key))
                else:
                    walk(v)
    for edge in edges:
        walk(edge['pattern'])
    if apply and changes:
        path.write_text(json.dumps(edges, indent=2, ensure_ascii=False) + '\n')
    return changes


def process(path: Path, apply: bool) -> list:
    _ACTIVE['groups'], _ACTIVE['do'] = {}, {}
    for key, over in FILE_OVERRIDES.items():
        if key in path.name:
            _ACTIVE['groups'], _ACTIVE['do'] = over['groups'], over['do']
    edges = json.loads(path.read_text(), object_pairs_hook=OrderedDict)
    changes: list = []
    for edge in edges:
        if edge.get('output_format') == HUB:
            edge['pattern'] = rename_pattern(edge['pattern'], changes)
        elif edge.get('input_format') == HUB:
            edge['pattern'] = drop_deleted(rename_input_pattern(edge['pattern'], changes))
    if '1815.2' in path.name:
        for edge in edges:
            fix_1815_2(edge, changes)
    for edge in edges:
        fix_connection_status(edge, changes)
    if apply and changes:
        path.write_text(json.dumps(edges, indent=2, ensure_ascii=False) + '\n')
    return changes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--transforms', default=str(Path(__file__).resolve().parents[1] / 'src' / 'interoperability' / 'transforms'))
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args(argv)
    files = sorted(p for p in Path(args.transforms).glob('*.json') if '61850' in p.name)
    total = 0
    for name in DIRECT_CONNECTION_STATUS:
        f = Path(args.transforms) / name
        if f.exists():
            changes = fix_direct_connection_status(f, args.apply)
            total += len(changes)
            print(f'{f.name}: direct-switch {len(changes)}')
    for f in files:
        changes = process(f, args.apply)
        kinds = {}
        for kind, *_ in changes:
            kinds[kind] = kinds.get(kind, 0) + 1
        total += len(changes)
        print(f'{f.name}: ' + ', '.join(f'{k} {n}' for k, n in sorted(kinds.items())) if changes else f'{f.name}: no change')
        for c in changes:
            if c[0] == 'CONFLICT' or args.verbose:
                print('   ', *c)
    print(f'{"applied" if args.apply else "would apply"} {total} changes in {len(files)} files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
