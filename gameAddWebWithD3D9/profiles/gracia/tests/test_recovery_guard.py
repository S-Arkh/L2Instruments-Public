"""Negative checks ensure the recovery verifier catches semantic/control changes."""
import copy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from verify_recovery import Package, verify

def rejected(original, modified):
    try:result=verify(original,modified)
    except ValueError:return
    if isinstance(result,dict):return
    raise AssertionError('Corrupted recovery was accepted')

def main():
    original=Package(ROOT/'inputs/Interface.u').function('PartyWndOption.OnShow')
    compiled=Package(ROOT/'workspace/System/Interface.u').function('PartyWndOption.OnShow')
    assert isinstance(verify(original,compiled),int)
    altered=copy.deepcopy(compiled)
    next(n for n in altered['instructions'] if n['kind']=='int_zero')['kind']='int_one'
    rejected(original,altered)
    altered=copy.deepcopy(compiled)
    next(n for n in altered['instructions'] if n.get('index')==150)['index']=151
    rejected(original,altered)
    altered=copy.deepcopy(compiled)
    jump=next(n for n in reversed(altered['instructions']) if n['kind']=='jump')
    jump['target']=0
    rejected(original,altered)
    print('PASS recovery verifier rejects changed initial PC, comparison operator and dispatcher backedge')

if __name__=='__main__':main()
