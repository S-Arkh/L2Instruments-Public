"""Reuse CFG verifier on the independently generated and recompiled Gracia classes."""
from pathlib import Path
import copy
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'gameAddWebWithD3D9/profiles/gracia'))
import verify_recovery as verifier
from bytecode_sources import Package, tree

def main():
    outputs=sorted(ROOT.glob('tests/compile-*/System/Interface.u'))
    if not outputs:raise RuntimeError('Run compile_recovered.py first')
    compiled=outputs[-1]
    source=Package(ROOT.parent/'gameAddWebWithD3D9/profiles/gracia/inputs/Interface.u')
    target=Package(compiled)
    canonical=verifier.canonical
    def normal(node):
        if node['kind']=='virtual_call' and node['value'].casefold()=='__uxcontextint':
            return ['context',*[normal(n) for n in node['children'] if n['kind']!='end_parameters']]
        if node['kind']=='class_context' and len(node['children'])==2:
            call=node['children'][1]
            if call['kind']=='virtual_call' and call['value'].casefold()=='__uxcontextint':
                return ['context',*[normal(n) for n in call['children'] if n['kind']!='end_parameters']]
        # A same-class static helper can compile as a final call.
        if node['kind']=='final_call' and node['value'].casefold().endswith('.__uxcontextint'):
            return ['context',*[normal(n) for n in node['children'] if n['kind']!='end_parameters']]
        return canonical(node)
    verifier.canonical=normal
    errors={};verified=0;blocks=0
    for i,e in enumerate(source.exports,1):
        if source.ref(e.cls)!='Core.Function':continue
        name=source.ref(i)
        try:
            a=source.function(name);b=target.function(name)
            assert a['flags']==b['flags'] and a['native']==b['native'],'Function ABI differs'
            # Standalone exporter does not insert the browser's login branch.
            a=copy.deepcopy(a);a['name']=a['name'].lower()
            if not a['native']:
                result=verifier.verify(a,b)
                if isinstance(result,dict):
                    errors[name]=result
                    continue
                blocks+=result
            verified+=1
        except Exception as error:errors[name]=str(error)
    helper=target.function('ClanDrawerWnd.__UXContextInt')
    nodes=tree(helper['instructions'])
    assert len(nodes)==4
    assert canonical(nodes[0]['children'][0])==['native',114,['local','clandrawerwnd.__uxcontextint.owner'],['none']]
    assert nodes[0]['target']==nodes[2]['pc']
    assert canonical(nodes[1])==['return',['int',0]]
    assert canonical(nodes[2])==['return',['local','clandrawerwnd.__uxcontextint.value']]
    old=verifier.Types(ROOT.parent/'gameAddWebWithD3D9/profiles/gracia/inputs', ('Interface',))
    new=verifier.Types(compiled.parent, ('Interface',))
    metadata_errors={}
    for name, prop in old.properties.items():
        other=new.properties.get(name,{})
        for key in ('kind','ref','flags','dim'):
            a,b=prop[key],other.get(key)
            if isinstance(a,str):a=a.casefold()
            if isinstance(b,str):b=b.casefold()
            if a!=b:metadata_errors[name+'.'+key]=[a,b]
    for category in ('parents','enums'):
        for name,value in getattr(old,category).items():
            other=getattr(new,category).get(name)
            if json.dumps(value).casefold()!=json.dumps(other).casefold():metadata_errors[category+':'+name]=[value,other]
    result={'original_sha256':source.sha256,'compiled_sha256':target.sha256,
            'compiled':str(compiled),'verified_functions':verified,'verified_blocks':blocks,
            'errors':errors,'metadata_errors':metadata_errors,'helper_verified':True,
            'passed':not errors and not metadata_errors}
    (ROOT/'tests/roundtrip-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return not result['passed']
if __name__=='__main__':raise SystemExit(main())
