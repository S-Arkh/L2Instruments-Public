"""Inventory target/donor UI without decrypting or modifying either client."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'gameAddWebWithD3D9/tools/ue2'),str(ROOT/'int64/tools')]
from ue2package import Package
from verify_profile import PE

def find(root,name):
    found=[p for p in root.iterdir() if p.is_file() and p.name.casefold()==name.casefold()]
    return found[0] if len(found)==1 else None

def describe(path):
    data=path.read_bytes();decoded=data;envelope='unknown'
    if data.startswith(b'ActiveAnticheatCrypt'):envelope='ActiveAnticheatCrypt (not decoded)'
    for marker in ('Lineage2Ver111','GamekitData111'):
        prefix=marker.encode('utf-16le')
        if data.startswith(prefix):
            envelope=marker;decoded=bytes(b^0xac for b in data[len(prefix):]);break
    result={'file':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
            'prefix_hex':data[:40].hex()}
    if path.suffix.casefold() in ('.u','.xdat'):
        result['envelope']=envelope
        if decoded[:4]==bytes.fromhex('c1832a9e'):
            result['package_version'],result['licensee_version']=struct.unpack_from('<HH',decoded,4)
            result['decoded_sha256']=hashlib.sha256(decoded).hexdigest()
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',type=Path,required=True);parser.add_argument('--donor',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    names=('Core.dll','Engine.dll','NWindow.dll','D3DDrv.dll','ExtensionL2.dll',
           'Core.u','Engine.u','NWindow.u','ExtensionL2.u','Interface.u','Interface.xdat')
    result={'target':{},'donor':{},'export_comparison':{},'original_clients_modified':False}
    for label,root in [('target',args.target),('donor',args.donor)]:
        for name in names:
            path=find(root,name)
            if path:result[label][name]=describe(path)
    package=Package(find(args.donor,'Interface.u'))
    classes=[e.name for e in package.exports if e.cls==0]
    result['donor_classes']={'count':len(classes),'browser_related':[n for n in classes if n in ('BrowserWnd','AddWebAPI','TextureProbeAPI')]}
    result['donor_root_imports']=[package.ref(-i) for i,e in enumerate(package.imports,1) if not e.outer]
    for name in ('Core.dll','Engine.dll','NWindow.dll','D3DDrv.dll'):
        a,b=PE(find(args.donor,name)),PE(find(args.target,name))
        result['export_comparison'][name]={'donor_count':len(a.exports),'target_count':len(b.exports),
            'missing_from_target':sorted(set(a.exports)-set(b.exports)),
            'target_only':sorted(set(b.exports)-set(a.exports))}
    result['limitations']=['Target protected UI/Engine/NWindow packages not decoded.',
        'Export-name overlap does not prove ABI or UI compatibility.',
        'Requested donor contains prior browser modifications; this is not a pristine HF baseline.']
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'donor_classes':result['donor_classes'],'donor_imports':result['donor_root_imports'],
        'target_ui_envelope':result['target']['Interface.u']['envelope'],'report':str(args.report)},indent=2))

if __name__=='__main__':main()
